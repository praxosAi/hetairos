from fastapi import APIRouter, Request, HTTPException
import logging
from src.core.event_queue import event_queue
from src.integrations.email.gmail_pubsub import gmail_pubsub_manager
from src.services.user_service import user_service
from src.integrations.email.gmail_client import GmailIntegration
from src.services.conversation_manager import ConversationManager
from src.utils.database import conversation_db
from src.services.integration_service import integration_service
router = APIRouter()
from src.utils.logging.base_logger import setup_logger,user_id_var, modality_var, request_id_var
logger = setup_logger(__name__)

@router.post("/gmail")
async def handle_gmail_webhook(request: Request):
    """
    Handles incoming Gmail push notifications via Google Cloud Pub/Sub.
    """

    body = await request.json()

    parsed_message = gmail_pubsub_manager.parse_pubsub_message(body)
    logging.info(f"Parsed Pub/Sub message: {parsed_message}")
    if not parsed_message or not gmail_pubsub_manager.validate_pubsub_message(parsed_message):
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub message")

    gmail_data = gmail_pubsub_manager.extract_gmail_notification_data(parsed_message)
    user_email = gmail_data.get("email_address")
    history_id = gmail_data.get("history_id")

    logger.info(f"Received Gmail webhook for user {user_email} with history ID {history_id}")

    user_ids = await integration_service.get_user_by_integration_name("gmail", user_email)

    if not user_ids:
        logger.error(f"No Gmail integration found for user {user_email}")
        return {"status": "error", "message": "No Gmail integration found"}
    
    gmail_integration = None
    for user_id in user_ids:
        gmail_integration = GmailIntegration(user_id)
        if not await gmail_integration.authenticate():
            logger.error(f"Failed to authenticate Gmail for user {user_id} and email {user_email}")
            continue
        logger.info(f"Gmail integration for user {user_id} is selected")
        break

    new_messages = await gmail_integration.get_history_since(history_id)

    if not new_messages:
        logger.info(f"No new messages found for user {user_email} with history ID {history_id}")
        return {"status": "ok"}
    
    logger.info(f"sending {len(new_messages)} new messages to the event queue for {len(user_ids)} users")

    for message in new_messages:
        input_text = f"New email from {message.get('from')}. Subject: {message.get('subject')}. Body: {message.get('snippet')}"

        for user_id in user_ids:
            user_id_var.set(str(user_id))
            modality_var.set("gmail")
            event = {
                "user_id": str(user_id),
                "source": "gmail",
                "payload": {"text": input_text},
                "logging_context": {'user_id': str(user_id), 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
                "metadata": {"gmail_message_id": message.get("id"), 'source':'gmail'}
            }
            await event_queue.publish(event)

    return {"status": "ok"}
