from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.core.praxos_client import PraxosClient
from src.utils.database import db_manager
from datetime import datetime, timezone
import json
import hmac
import hashlib
import os

logger = setup_logger(__name__)
router = APIRouter()

def verify_notion_signature(body: bytes, signature: str, timestamp: str) -> bool:
    """
    Verify Notion webhook signature using HMAC-SHA256.

    Args:
        body: Raw request body bytes
        signature: Signature from Notion-Signature header
        timestamp: Timestamp from Notion-Signature header

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Get Notion webhook secret from environment
        secret = os.getenv("NOTION_WEBHOOK_SECRET")
        if not secret:
            logger.warning("NOTION_WEBHOOK_SECRET not set - skipping signature verification")
            return True  # Allow for development, but should be required in production

        # Notion signature format: v1=timestamp:signature
        # Compute HMAC-SHA256(secret, timestamp.body)
        message = f"{timestamp}.{body.decode('utf-8')}"
        computed = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        expected = f"v1={computed}"

        # Timing-safe comparison
        return hmac.compare_digest(expected, signature)

    except Exception as e:
        logger.error(f"Error verifying Notion signature: {e}")
        return False

@router.post("/notion")
async def handle_notion_webhook(request: Request):
    """
    Handles incoming Notion webhooks (API version 2025-09-03).

    Notion sends webhooks for page, database, and data_source events.
    Reference: https://developers.notion.com/reference/webhooks

    Verification Process:
    1. Configure webhook in Notion integration settings
    2. Notion sends POST with verification_token
    3. Display the token in logs
    4. Paste token back into Notion UI to complete verification
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        data = json.loads(body.decode('utf-8'))

        logger.info(f"Received Notion webhook: {json.dumps(data, indent=2)}")

        # Handle verification request
        # Notion sends verification_token that must be entered in Notion UI
        if "verification_token" in data:
            token = data["verification_token"]
            logger.info("=" * 80)
            logger.info("NOTION WEBHOOK VERIFICATION")
            logger.info("=" * 80)
            logger.info(f"Verification Token: {token}")
            logger.info("Copy this token and paste it into Notion integration settings:")
            logger.info("1. Go to https://www.notion.so/profile/integrations")
            logger.info("2. Select your integration")
            logger.info("3. Go to Webhooks tab")
            logger.info("4. Click 'Verify' and paste the token above")
            logger.info("=" * 80)

            # Return 200 OK to acknowledge receipt
            return Response(status_code=200)

        # Verify signature for production webhooks (optional but recommended)
        signature = request.headers.get("Notion-Signature")
        timestamp = request.headers.get("Notion-Timestamp")

        if signature and timestamp:
            if not verify_notion_signature(body, signature, timestamp):
                logger.warning("Invalid Notion webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Process webhook events
        # Supported events: page.*, database.*, data_source.*
        event_type = data.get("type")  # e.g., "page.created", "page.updated", "page.deleted"

        if not event_type:
            logger.warning("No event type in Notion webhook")
            return {"status": "ok"}

        # Extract workspace/bot info
        workspace_id = data.get("workspace_id")
        bot_id = data.get("bot_id")

        # Find user by workspace_id or bot_id
        # Bot ID is stored in integration.metadata.webhook_info.bot_id
        user_id = await integration_service.get_user_by_notion_bot_id(bot_id)

        if not user_id:
            logger.warning(f"No user found for Notion bot ID: {bot_id}")
            return {"status": "ok"}

        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            logger.error(f"User not found for ID {user_id}")
            return {"status": "ok"}

        user_id_var.set(str(user_id))
        modality_var.set("notion_webhook")

        # Extract page/database/data_source details
        page_id = data.get("page_id")
        database_id = data.get("database_id")
        data_source_id = data.get("data_source_id")

        # Create PraxosClient for trigger evaluation
        praxos_api_key = user_record.get("praxos_api_key")
        praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

        # Evaluate triggers using the full event data
        logger.info(f"Evaluating triggers for Notion event {event_type}")
        event_eval_result = await praxos_client.eval_event(data, 'notion_event')

        if event_eval_result.get('trigger'):
            # Trigger fired - publish triggered event
            for rule_id, action_data_list in event_eval_result.get('fired_rule_actions_details', {}).items():
                if isinstance(action_data_list, str):
                    action_data_list = json.loads(action_data_list)

                rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                if not rule_details:
                    logger.error(f"No trigger details found in DB for rule_id {rule_id}. Trigger may be inactive, deleted, or flawed.")
                    continue

                # Build COMMAND for triggered event
                COMMAND = ""
                COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                COMMAND += f"Now, upon receiving a Notion page/database change at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                for action_item in action_data_list:
                    COMMAND += "The following action was marked as a triggering candidate: " + action_item.get('simple_sentence', '') + ". \n"
                    COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action_item, default=str) + ". \n\n"
                COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. If you are unsure about any action, please ask the user for confirmation before proceeding. \n\n The event (Notion change, in this case) that triggered this action is as follows: "

                # Build triggered event with COMMAND prefix
                triggered_event = {
                    "user_id": str(user_id),
                    "source": "triggered",
                    "payload": {
                        "text": COMMAND + json.dumps({
                            "event_type": event_type,
                            "workspace_id": workspace_id,
                            "bot_id": bot_id,
                            "page_id": page_id,
                            "database_id": database_id,
                            "data_source_id": data_source_id,
                            "full_data": data
                        }, default=str)
                    },
                    "logging_context": {
                        "user_id": user_id_var.get(),
                        "request_id": str(request_id_var.get()),
                        "modality": "triggered",
                    },
                    "metadata": {
                        'ingest_type': 'notion_webhook_triggered',
                        'source': 'notion',
                        'webhook_event': True,
                        'event_type': event_type,
                        'workspace_id': workspace_id,
                        'page_id': page_id,
                        'database_id': database_id,
                        'conversation_id': rule_details.get('conversation_id'),
                    }
                }

                if not triggered_event["metadata"].get("conversation_id"):
                    triggered_event['metadata'].pop('conversation_id', None)

                await event_queue.publish(triggered_event)
                logger.info(f"Published triggered event for Notion event {event_type} based on rule {rule_id}")
        else:
            logger.info(f"Evaluation found no trigger for Notion event {event_type}. Proceeding with normal ingestion.")

        # Notion includes full page/database data in webhook (unlike OneDrive)
        event = {
            "user_id": str(user_id),
            "source": "event_ingestion",
            "payload": {
                "event_type": event_type,
                "workspace_id": workspace_id,
                "bot_id": bot_id,
                "page_id": page_id,
                "database_id": database_id,
                "data_source_id": data_source_id,
                "full_data": data
            },
            "logging_context": {
                'user_id': user_id_var.get(),
                'request_id': str(request_id_var.get()),
                'modality': 'notion_webhook'
            },
            "metadata": {
                'ingest_type': 'notion_webhook',
                'source': 'notion',
                'webhook_event': True,
                'event_type': event_type,
                'workspace_id': workspace_id
            }
        }

        # await event_queue.publish(event)
        logger.info(f"Processed Notion webhook for user {user_id}, event_type: {event_type}")

        return {"status": "ok"}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Notion webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Notion webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
