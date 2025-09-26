from fastapi import APIRouter, Request, HTTPException, Response
from src.integrations.email.email_bot_client import OutlookBotMessage
from typing import List, Optional
import aiohttp
import json
import re
from src.services.integration_service import integration_service

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
    if validation_token:
        webhook_logger.info("Responding to Outlook validation request.")
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    webhook_logger.info("Received Outlook notification webhook.")
    body = await request.json()
    
    for notification in body.get("value", []):
        if notification.get("clientState") != settings.OUTLOOK_VALIDATION_TOKEN:
            webhook_logger.warning("Invalid clientState in notification. Ignoring.")
            continue

        if notification.get("changeType") == "created":
            resource = notification.get("resource")
            ms_user_id = _extract_ms_user_id(resource) if resource else None
            if not ms_user_id:
                webhook_logger.warning(f"Could not extract MS user ID from resource: {resource}")
                continue
            
            user_record = user_service.get_user_by_ms_id(ms_user_id)
            if not user_record:
                webhook_logger.warning(f"No user found for MS Graph ID: {ms_user_id}")
                continue
            ### todo, this is for ingest/filtering.
            # event = {
            #     "user_id": str(user_record["_id"]),
            #     "source": "outlook",
            #     "payload": {"resource": resource, "subscription_id": notification.get("subscriptionId")},
            #     "metadata": {"change_type": "created"},
            #     'output_type': 'email',
            #     'email_type': 'new',
            # }
            # await event_queue.publish(event)
            webhook_logger.info(f"Queued Outlook email event for user {user_record['_id']}")

    return {"status": "ok"}

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
