from fastapi import APIRouter, Request, HTTPException
import logging
from src.core.event_queue import event_queue
from src.integrations.email.gmail_pubsub import gmail_pubsub_manager
from src.services.user_service import user_service
from src.integrations.email.gmail_client import GmailIntegration
from src.services.conversation_manager import ConversationManager
from src.utils.database import conversation_db
from src.core.praxos_client import PraxosClient
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
    logger.info(f"Parsed Pub/Sub message: {parsed_message}")
    if not parsed_message or not gmail_pubsub_manager.validate_pubsub_message(parsed_message):
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub message")

    gmail_data = gmail_pubsub_manager.extract_gmail_notification_data(parsed_message)
    user_email = gmail_data.get("email_address")
    history_id = gmail_data.get("history_id")

    logger.info(f"Received Gmail webhook for user {user_email} with history ID {history_id}")

    user_id = await integration_service.get_user_by_integration("gmail", user_email)
    user_id = user_id[0]
    if not user_id:
        logger.error(f"No Gmail integration found for user {user_email}")
        return {"status": "error", "message": "No Gmail integration found"}
    user_record = await user_service.get_user_by_id(user_id)
    if not user_record:
        logger.error(f"User not found for ID {user_id}")
        return {"status": "error", "message": "User not found"}

    try:
        gmail_integration = GmailIntegration(user_id)
        if not await gmail_integration.authenticate():
            logger.error(f"Failed to authenticate Gmail for user {user_id} and email {user_email}")
            return {"status": "error", "message": "Failed to authenticate Gmail"}
    except Exception as e:
        logger.error(f"Exception during Gmail authentication for user {user_id} and email {user_email}: {e}")
        return {"status": "error", "message": "Exception during Gmail authentication"}

    message_ids, new_checkpoint = gmail_integration.get_changed_message_ids_since(history_id)
    new_messages = []
    if message_ids:
        new_messages = gmail_integration.get_messages_by_ids(message_ids, user_id="me")
    logger.info(f"New messages: {new_messages}")
    if not new_messages:
        logger.info(f"No new messages found for user {user_email} with history ID {history_id}")
        return {"status": "ok"}
    
    message_new_flags = await conversation_db.insert_or_reject_emails(new_messages, user_id)
    if all(flag is False for flag in message_new_flags):
        logger.info(f"All messages already processed for user {user_email} with history ID {history_id}")
        return {"status": "ok"}
    
    praxos_api_key = user_record.get("praxos_api_key")
    praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)
    for message,message_new_flag in zip(new_messages,message_new_flags):
        if not message_new_flag:
            logger.info(f"Message {message.get('id')} already processed, skipping.")
            continue
        logger.info(f"Processing new message {message.get('id')}")
        ### here, we want to have idempotency to prevent processing the same email multiple times
        event_eval_result = await praxos_client.eval_event(message,'gmail')
        logger.info(f"Event evaluation result: {event_eval_result}")
        # for user_id in user_ids:
        #     user_id_var.set(str(user_id))
        #     modality_var.set("gmail")
            
        #     event = {
        #         "user_id": str(user_id),
        #         "source": "gmail",
        #         "payload": {"text": input_text},
        #         "logging_context": {'user_id': str(user_id), 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
        #         "metadata": {"gmail_message_id": message.get("id"), 'source':'gmail'}
        #     }
        #     await event_queue.publish(event)

    return {"status": "ok"}
