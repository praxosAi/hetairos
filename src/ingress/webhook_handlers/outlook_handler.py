from fastapi import APIRouter, Request, HTTPException, Response
from src.integrations.email.email_bot_client import OutlookBotMessage
from typing import List, Optional,Dict, Any
import aiohttp
import json
from src.utils.database import db_manager
import re
from src.services.integration_service import integration_service
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration,extract_ms_ids_from_resource
from src.core.praxos_client import PraxosClient
from src.core.event_queue import event_queue
from src.utils.logging.base_logger import setup_logger,user_id_var, modality_var, request_id_var
from src.config.settings import settings
from src.services.user_service import user_service
from src.egress.service import egress_service
router = APIRouter()

# --- Pydantic Models for Bot Webhook ---


# --- Helper Functions ---
def _extract_ms_user_id(resource: str) -> str | None:
    """Extracts the Microsoft Graph user ID from the resource URL."""
    match = re.search(r"users/([^/]+)/", resource)
    return match.group(1) if match else None


### @TODO move to egress.

webhook_logger = setup_logger("outlook_webhook")
# --- Webhook Endpoints ---
@router.post("/outlook")
async def handle_outlook_webhook(request: Request):
    """Handle incoming Outlook webhooks for user subscriptions."""
    validation_token = request.query_params.get("validationToken")
    modality_var.set("outlook_webhook")

    # Validation handshake
    if validation_token:
        webhook_logger.info("Responding to Outlook validation request.")
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    webhook_logger.info("Received Outlook notification webhook.")
    body = await request.json()
    webhook_logger.info(f"Webhook body: {json.dumps(body)}")
    # Graph sends { "value": [ ... notifications ... ] }
    notifications: List[Dict[str, Any]] = body.get("value", [])
    if not notifications:
        webhook_logger.warning("No notifications found in webhook body.")
        return {"status": "ok", "fetched": 0}

    processed = 0
    inserted = 0

    for notification in notifications:
        # Verify clientState
        if notification.get("clientState") != settings.OUTLOOK_VALIDATION_TOKEN:
            webhook_logger.warning("Invalid clientState in notification. Ignoring.")
            continue

        # Only handle created messages? 
        if notification.get("changeType") not in ("created", "updated"):
            continue

        resource = notification.get("resource")

        ms_user_id, msg_id = extract_ms_ids_from_resource(resource or "")
        webhook_logger.info(f"Parsed ms_user_id: {ms_user_id}, msg_id: {msg_id} from resource: {resource}")
        if not ms_user_id or not msg_id:
            webhook_logger.warning(f"Could not parse ms_user_id/msg_id from resource: {resource}")
            continue

        # Find your app user by the stored Microsoft Graph user id
        # user_record = user_service.get_user_by_ms_id(ms_user_id)
        user_id = await integration_service.get_user_by_ms_id(ms_user_id)
        user_record = user_service.get_user_by_id(user_id) if user_id else None
        praxos_api_key = user_record.get("praxos_api_key")
        praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)
        if not user_record:
            webhook_logger.warning(f"No user found for MS Graph ID: {ms_user_id}")
            continue

        user_id = str(user_record["_id"])
        processed += 1

        # Authenticate client
        outlook = MicrosoftGraphIntegration(user_id)
        if not await outlook.authenticate():
            webhook_logger.error(f"Outlook auth failed for user {user_id} (ms_id={ms_user_id})")
            continue
        
        # Fetch + normalize (OPTIONAL: add a command prefix)
        COMMAND = ""  # fill if you want to prepend trigger text
        try:

            already_exists = await db_manager.check_platform_and_message_id_exists('outlook', msg_id, user_id)
            if already_exists:
                webhook_logger.info(f"Outlook message {msg_id} already processed for user {user_id}; skipping.")
                continue
            normalized = await outlook.normalize_message_for_ingestion(
                user_record=user_record,
                ms_user_id=ms_user_id,
                message_id=msg_id,
                command_prefix=COMMAND,
            )
        except Exception as e:
            webhook_logger.error(f"Failed to fetch/normalize message {msg_id}: {e}", exc_info=True)
            continue

        # Idempotent insert in 'documents' or your emails collection (same method you used for Gmail)
        # Here we pass the *raw* Graph message is not available anymore, but our normalizer
        # didn't return the raw; so we store a minimal record for dedupe:
        # Option A: change insert_or_reject_emails to accept normalized dicts and look up platform_message_id from normalized["id"].
        # Option B: fetch the raw message again, or build a small dict that includes {"id": msg_id}.
        to_insert = {"id": normalized["id"], "normalized": normalized}
        to_insert['user_id'] = user_id
        inserted_ids = await db_manager.insert_new_outlook_email(to_insert)
        inserted_id = inserted_ids[0] if inserted_ids else None
        
        if not inserted_id:
            webhook_logger.info(f"Outlook message {msg_id} already processed; skipping.")
            continue

        inserted += 1

        # Attach inserted doc id to metadata
        normalized["metadata"]["inserted_id"] = inserted_id
        webhook_logger.info(f"eval event, normalized: {json.dumps(normalized)}")
        event_eval_result = await praxos_client.eval_event(normalized, 'outlook')
        webhook_logger.info(f"Event eval result: {event_eval_result}")
        # Build event like WhatsApp/Gmail
        user_id_var.set(user_id)
        event = {
            "user_id": user_id,
            "source": "event_ingestion",
            "payload": normalized["payload"],  # text + files
            "logging_context": {
                "user_id": user_id_var.get(),
                "request_id": str(request_id_var.get()),
                "modality": "ingestion_api",
            },
            "metadata": {
                **normalized["metadata"],
                "subject": normalized["subject"],
                "from": normalized["from"],
                "to": normalized["to"],
                "thread_id": normalized["thread_id"],
            },
        }

        # Optional: evaluate + enqueue like Gmail
        # await event_queue.publish(event)

    return {"status": "ok", "processed": processed, "inserted": inserted}

@router.post("/outlook-bot")
async def handle_outlook_bot_webhook(message: OutlookBotMessage):
    """Handle direct emails sent to the bot's address (e.g., my@praxos.ai)."""
    webhook_logger.info(f"Received bot email from: {message.from_sender.address}")
    webhook_logger.info(f"Message: {json.dumps(message.dict(by_alias=True))}")
    modality_var.set("outlook_bot_webhook")
    sender_email = message.from_sender.address
    user_record = None
    user_record = user_service.get_user_by_email(sender_email)
    if not user_record:
        user_integration = await integration_service.get_user_by_integration("email", sender_email)
        if user_integration:
            user_record = user_service.get_user_by_id(user_integration[0])

    
    if user_record:
        user_id_var.set(str(user_record["_id"]))
        webhook_logger.info(f"Sender {sender_email} is a registered user.")
        ### @TODO, this should use html parsing to get the text.
        event_text = message.bodyPreview
        event = {
            "user_id": str(user_record["_id"]),
            "source": "email",
            "output_type": "email",
            "email_type": "reply",
            "logging_context": {'user_id': str(user_record["_id"]), 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
            "payload": {"text": event_text, "raw_email": message.dict(by_alias=True)},
            "metadata": {"message_id": message.messageId, "source": "bot-direct-email","original_message": message.dict(by_alias=True)}
        }
        await event_queue.publish(event)
        webhook_logger.info(f"Queued direct email event for user {str(user_record['_id'])} with event text {event_text}")

    else:
        webhook_logger.warning(f"Sender {sender_email} is not a registered user. Sending reply.")
        await egress_service.send_response({"source": "outlook_bot", "output_type": "email", "email_type": "unauthorised_user","original_message": message}, {})
    return {"status": "ok"}
