from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.core.praxos_client import PraxosClient
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.utils.database import db_manager
from datetime import datetime, timezone
import json
import hmac
import hashlib
import os

router = APIRouter()
logger = setup_logger(__name__)

def verify_dropbox_signature(body: bytes, signature: str) -> bool:
    """
    Verify Dropbox webhook signature using HMAC-SHA256.

    Args:
        body: Raw request body bytes
        signature: Signature from X-Dropbox-Signature header

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Get Dropbox app secret from environment
        app_secret = os.getenv("DROPBOX_APP_SECRET")
        if not app_secret:
            logger.warning("DROPBOX_APP_SECRET not set - skipping signature verification")
            return True  # Allow for development, but should be required in production

        # Compute HMAC-SHA256
        computed = hmac.new(
            app_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()

        # Timing-safe comparison
        return hmac.compare_digest(computed, signature)

    except Exception as e:
        logger.error(f"Error verifying Dropbox signature: {e}")
        return False

@router.get("/dropbox")
async def handle_dropbox_verification(request: Request):
    """
    Handles Dropbox webhook verification (challenge request).

    Dropbox sends GET request with challenge parameter.
    We must echo back the challenge to verify endpoint ownership.
    """
    challenge = request.query_params.get("challenge")

    if challenge:
        logger.info("=" * 80)
        logger.info("DROPBOX WEBHOOK VERIFICATION")
        logger.info("=" * 80)
        logger.info(f"Received challenge: {challenge}")
        logger.info("Responding with challenge to verify endpoint")
        logger.info("=" * 80)

        # Echo back the challenge
        return Response(
            content=challenge,
            media_type="text/plain",
            status_code=200,
            headers={"Content-Type": "text/plain", "X-Content-Type-Options": "nosniff"}
        )

    logger.warning("Dropbox GET request without challenge parameter")
    return Response(status_code=400, content="Missing challenge parameter")

@router.post("/dropbox")
async def handle_dropbox_webhook(request: Request):
    """
    Handles incoming Dropbox webhook notifications.

    Dropbox webhooks are APP-LEVEL (not per-user).
    All users share the same webhook URL configured in Dropbox App Console.
    Reference: https://www.dropbox.com/developers/reference/webhooks

    IMPORTANT: Dropbox only sends user account IDs, not file details.
    You must call /files/list_folder/continue with stored cursor to get changes.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature
        signature = request.headers.get("X-Dropbox-Signature")
        if signature:
            if not verify_dropbox_signature(body, signature):
                logger.warning("Invalid Dropbox webhook signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse JSON body
        data = json.loads(body.decode('utf-8'))

        logger.info(f"Received Dropbox webhook notification: {json.dumps(data, indent=2)}")

        # Extract accounts with changes
        # Format: {"list_folder": {"accounts": ["dbid:xxx", "dbid:yyy"]}}
        # Or: {"delta": {"users": [12345, 67890]}}
        accounts = []

        if "list_folder" in data:
            accounts = data["list_folder"].get("accounts", [])
        elif "delta" in data:
            # Older format
            accounts = [f"dbid:{uid}" for uid in data["delta"].get("users", [])]

        if not accounts:
            logger.warning("No accounts in Dropbox webhook notification")
            return {"status": "ok"}

        logger.info(f"Dropbox changes for {len(accounts)} account(s): {accounts}")

        # Track processing stats
        processed_accounts = 0
        total_files_fetched = 0
        total_files_inserted = 0

        # Process each account
        for account_id in accounts:
            try:
                # Find user by Dropbox account ID
                # Account ID is stored in integration.metadata.webhook_info.account_id
                result = await integration_service.get_user_by_dropbox_account_id(account_id)

                if not result:
                    logger.warning(f"No user found for Dropbox account ID: {account_id}")
                    continue

                user_id, connected_account = result

                user_record = user_service.get_user_by_id(user_id)
                if not user_record:
                    logger.error(f"User not found for ID {user_id}")
                    continue

                # Set logging context
                user_id_var.set(str(user_id))
                modality_var.set("dropbox_webhook")

                logger.info(f"Processing Dropbox webhook for user {user_id}, account: {account_id}")

                # Initialize Dropbox integration
                from src.integrations.dropbox.dropbox_client import DropboxIntegration
                dropbox_integration = DropboxIntegration(user_id)
                if not await dropbox_integration.authenticate():
                    logger.error(f"Failed to authenticate Dropbox for user {user_id} and account {account_id}")
                    continue

                # Get checkpoint (cursor)
                checkpoint = await integration_service.get_dropbox_cursor(user_id, connected_account)

                if not checkpoint:
                    # Seed once: store current cursor and exit (no backfill)
                    _, new_cursor = await dropbox_integration.get_changed_files_since(
                        cursor=None,
                        account=connected_account
                    )
                    if new_cursor:
                        await integration_service.set_dropbox_cursor(user_id, connected_account, new_cursor)
                        logger.info(f"Seeded Dropbox cursor for {connected_account} at {new_cursor}")
                    continue

                # Fetch changed files since cursor
                changed_files, new_cursor = await dropbox_integration.get_changed_files_since(
                    cursor=checkpoint,
                    account=connected_account
                )

                # Update cursor
                if new_cursor:
                    await integration_service.set_dropbox_cursor(user_id, connected_account, new_cursor)

                if not changed_files:
                    logger.info(f"No new files for {connected_account} since checkpoint {checkpoint} (advanced_to={new_cursor})")
                    continue

                total_files_fetched += len(changed_files)

                # Deduplicate using insert_or_reject_items
                from src.utils.database import db_manager
                inserted_ids = await db_manager.insert_or_reject_items(
                    items=changed_files,
                    user_id=user_id,
                    platform="dropbox",
                    id_field="id",
                    platform_id_field="platform_file_id"
                )

                inserted = [iid for iid in inserted_ids if iid]
                total_files_inserted += len(inserted)
                logger.info(f"Fetched {len(changed_files)} files; inserted {len(inserted)} for {connected_account}")

                # Process only those actually inserted
                praxos_api_key = user_record.get("praxos_api_key")
                praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

                # Publish new files to event queue with trigger evaluation
                for file, inserted_id in zip(changed_files, inserted_ids):
                    if not inserted_id:
                        logger.info(f"File {file.get('id')} already processed, skipping.")
                        continue

                    logger.info(f"Processing new file {file.get('id')}")

                    # Evaluate triggers for this file
                    event_eval_result = await praxos_client.eval_event(file, 'file_change')

                    if event_eval_result.get('trigger'):
                        # Process triggered actions (following Gmail pattern)
                        for rule_id, action_data in event_eval_result.get('fired_rule_actions_details', {}).items():
                            if isinstance(action_data, str):
                                action_data = json.loads(action_data)

                            rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                            if not rule_details:
                                logger.error(f"No trigger details found in DB for rule_id {rule_id}.")
                                continue

                            COMMAND = ""
                            COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                            COMMAND += f"Now, upon receiving a file change in Dropbox, at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                            for action in action_data:
                                COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                                COMMAND += "The action has the following details: " + json.dumps(action, default=str) + ". \n\n"
                            COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger. \n\n The event (Dropbox file change) that triggered this action is as follows: "

                            # Format file event
                            file_name = file.get('name', 'Unknown File')
                            file_path = file.get('path', '')
                            file_size = file.get('size', 0)

                            normalized = {
                                "payload": {
                                    "text": f"{COMMAND}\n\nFile: {file_name}\nPath: {file_path}\nSize: {file_size} bytes",
                                    "raw_file": file
                                },
                                "metadata": {
                                    "file_id": file.get('id'),
                                    "file_name": file_name,
                                    "file_path": file_path,
                                    "source": "dropbox"
                                }
                            }

                            triggered_event = {
                                "user_id": str(user_id),
                                "source": "triggered",
                                "payload": normalized["payload"],
                                "logging_context": {
                                    "user_id": user_id_var.get(),
                                    "request_id": str(request_id_var.get()),
                                    "modality": "triggered",
                                },
                                "metadata": {
                                    **normalized["metadata"],
                                    "conversation_id": rule_details.get('conversation_id'),
                                },
                            }
                            if not triggered_event["metadata"].get("conversation_id"):
                                triggered_event['metadata'].pop('conversation_id', None)

                            await event_queue.publish(triggered_event)
                            logger.info(f"Published triggered event for file {file.get('id')} based on rule {rule_id}")
                    else:
                        logger.info(f"No trigger found for file {file.get('id')}.")

                    # Normal ingestion event
                    if file.get('metadata') is None:
                        file['metadata'] = {}
                    file['metadata']['inserted_id'] = inserted_id

                    ingestion_event = {
                        "user_id": str(user_id),
                        "source": "event_ingestion",
                        "payload": file,
                        "logging_context": {
                            'user_id': user_id_var.get(),
                            'request_id': str(request_id_var.get()),
                            'modality': 'dropbox_webhook'
                        },
                        "metadata": {
                            'ingest_type': 'dropbox_webhook',
                            'source': 'dropbox',
                            'webhook_event': True,
                            'dropbox_file_id': file.get("id"),
                            'inserted_id': inserted_id,
                            'account': connected_account
                        }
                    }

                    # Publish to event queue
                    # await event_queue.publish(ingestion_event)

                processed_accounts += 1

            except Exception as e:
                logger.error(f"Error processing Dropbox account {account_id}: {e}", exc_info=True)
                continue

        logger.info(f"Dropbox webhook processing complete: {processed_accounts} accounts, {total_files_fetched} files fetched, {total_files_inserted} inserted")

        return Response(status_code=200)

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Dropbox webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Dropbox webhook: {e}", exc_info=True)
        return Response(status_code=200)  # Always return 200 to acknowledge webhook
