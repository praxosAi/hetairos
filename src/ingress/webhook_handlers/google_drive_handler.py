from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.integrations.gdrive.gdrive_client import GoogleDriveIntegration
from src.utils.database import db_manager
from src.core.praxos_client import PraxosClient
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from datetime import datetime, timezone
import json

router = APIRouter()
logger = setup_logger(__name__)

@router.post("/google-drive")
async def handle_google_drive_webhook(request: Request):
    """
    Handles incoming Google Drive push notifications.

    Google Drive sends notifications when files change.
    Reference: https://developers.google.com/drive/api/guides/push
    """
    try:
        # Google Drive sends notifications via headers, not body
        resource_id = request.headers.get("x-goog-resource-id")
        resource_state = request.headers.get("x-goog-resource-state")  # "sync", "update", "trash", "change"
        channel_id = request.headers.get("x-goog-channel-id")
        channel_token = request.headers.get("x-goog-channel-token")  # Optional verification token
        changed = request.headers.get("x-goog-changed")  # What changed: "properties", "content", "parents"

        logger.info(f"Received Google Drive webhook - Resource ID: {resource_id}, State: {resource_state}, Changed: {changed}, Channel: {channel_id}")

        # Sync notification is sent when watch is first created - acknowledge it
        if resource_state == "sync":
            logger.info("Received Google Drive sync notification (initial handshake)")
            return {"status": "ok"}

        # No resource ID means invalid notification
        if not resource_id or not channel_id:
            logger.warning("Missing required headers in Google Drive webhook")
            raise HTTPException(status_code=400, detail="Missing required headers")

        # Find user and connected_account by integration resource_id
        result = await integration_service.get_user_and_account_by_webhook_resource_id(resource_id, "google_drive")

        if not result:
            logger.warning(f"No user found for Google Drive resource ID: {resource_id}")
            return {"status": "ok"}  # Return OK to acknowledge webhook

        user_id, connected_account = result

        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            logger.error(f"User not found for ID {user_id}")
            return {"status": "ok"}

        user_id_var.set(str(user_id))
        modality_var.set("google_drive_webhook")

        logger.info(f"Processing Google Drive webhook for user {user_id}, account {connected_account}")

        # Initialize Google Drive client
        try:
            drive_integration = GoogleDriveIntegration(user_id)
            if not await drive_integration.authenticate():
                logger.error(f"Failed to authenticate Google Drive for user {user_id} and account {connected_account}")
                return {"status": "error", "message": "Failed to authenticate Google Drive"}
        except Exception as e:
            logger.error(f"Exception during Google Drive authentication for user {user_id} and account {connected_account}: {e}")
            return {"status": "error", "message": "Exception during Google Drive authentication"}

        # Get checkpoint (page token)
        checkpoint = await integration_service.get_drive_page_token(user_id, connected_account)

        if not checkpoint:
            # Seed once: store current page token and exit (no backfill)
            changed_files, new_page_token = await drive_integration.get_changed_files_since(None, account=connected_account)
            await integration_service.set_drive_page_token(user_id, connected_account, new_page_token)
            logger.info(f"Seeded Google Drive page token for {connected_account} at {new_page_token}")
            return {"status": "seeded"}

        # Fetch changed files since checkpoint using Changes API
        changed_files, new_page_token = await drive_integration.get_changed_files_since(
            checkpoint,
            account=connected_account
        )

        # Update checkpoint
        if new_page_token:
            await integration_service.set_drive_page_token(user_id, connected_account, new_page_token)

        if not changed_files:
            logger.info(f"No new files for {connected_account} since checkpoint {checkpoint} (advanced_to={new_page_token})")
            return {"status": "ok", "fetched": 0, "advanced_to": new_page_token}

        # Deduplicate using insert_or_reject_items
        inserted_ids = await db_manager.insert_or_reject_items(
            items=changed_files,
            user_id=user_id,
            platform="google_drive",
            id_field="id",
            platform_id_field="platform_file_id"
        )

        inserted = [iid for iid in inserted_ids if iid]
        logger.info(f"Fetched {len(changed_files)} files; inserted {len(inserted)} for {connected_account}")

        # Process only those actually inserted
        praxos_api_key = user_record.get("praxos_api_key")
        praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

        # For each new file: evaluate triggers and publish to event queue
        for file_data, inserted_id in zip(changed_files, inserted_ids):
            if not inserted_id:
                logger.info(f"File {file_data.get('id')} already processed, skipping.")
                continue

            logger.info(f"Processing new file {file_data.get('id')}")

            # Evaluate triggers for this file
            event_eval_result = await praxos_client.eval_event(file_data, 'file_change')

            if event_eval_result.get('trigger'):
                # Process triggered actions (following Gmail pattern)
                for rule_id, action_data in event_eval_result.get('fired_rule_actions_details', {}).items():
                    if isinstance(action_data, str):
                        action_data = json.loads(action_data)

                    rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                    if not rule_details:
                        logger.error(f"No trigger details found in DB for rule_id {rule_id}. trigger may be inactive, deleted, or flawed.")
                        continue

                    COMMAND = ""
                    COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                    COMMAND += f"Now, upon receiving a file change in Google Drive, at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action in action_data:
                        COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                        COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action, default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. If you are unsure about any action, please ask the user for confirmation before proceeding. \n\n The event (file change, in this case) that triggered this action is as follows: "

                    # Format file event for ingestion
                    file_name = file_data.get('name', 'Unknown File')
                    file_type = file_data.get('mimeType', '')
                    modified_time = file_data.get('modifiedTime', '')

                    normalized = {
                        "payload": {
                            "text": f"{COMMAND}\n\nFile: {file_name}\nType: {file_type}\nModified: {modified_time}",
                            "raw_file": file_data
                        },
                        "metadata": {
                            "file_id": file_data.get('id'),
                            "file_name": file_name,
                            "file_type": file_type,
                            "source": "google_drive"
                        }
                    }

                    ingestion_event = {
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
                    if not ingestion_event["metadata"].get("conversation_id"):
                        ingestion_event['metadata'].pop('conversation_id', None)

                    await event_queue.publish(ingestion_event)
                    logger.info(f"Published triggered event for file {file_data.get('id')} based on rule {rule_id}")
            else:
                logger.info(f"Evaluation found no trigger for file {file_data.get('id')}. Proceeding with normal ingestion.")

            # Normal ingestion event
            user_id_var.set(str(user_id))
            modality_var.set("google_drive_webhook")
            if file_data.get('metadata') is None:
                file_data['metadata'] = {}
            file_data['metadata']['inserted_id'] = inserted_id

            ingestion_event = {
                "user_id": str(user_id),
                "source": "event_ingestion",
                "payload": file_data,
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'ingestion_api'
                },
                "metadata": {
                    'ingest_type': 'google_drive_webhook',
                    'source': 'google_drive',
                    'google_drive_webhook_event': True,
                    'google_drive_file_id': file_data.get("id"),
                    'inserted_id': inserted_id,
                    'connected_account': connected_account
                }
            }
            # await event_queue.publish(ingestion_event)

        return {
            "status": "ok",
            "fetched": len(changed_files),
            "inserted": len(inserted),
            "advanced_to": new_page_token
        }

    except Exception as e:
        logger.error(f"Error processing Google Drive webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
