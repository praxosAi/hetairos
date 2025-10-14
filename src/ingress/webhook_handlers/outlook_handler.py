from fastapi import APIRouter, Request, Response, BackgroundTasks, status, HTTPException
from src.integrations.email.email_bot_client import OutlookBotMessage
from typing import List, Optional, Dict, Any
import json
import asyncio

from src.utils.database import db_manager
from src.services.integration_service import integration_service
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration, extract_ms_ids_from_resource
from src.core.praxos_client import PraxosClient
from src.core.event_queue import event_queue
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.config.settings import settings
from src.services.user_service import user_service
from src.egress.service import egress_service

router = APIRouter()
webhook_logger = setup_logger("outlook_webhook")


# --- Background Worker Function ---

async def process_notification_task(notification: Dict[str, Any]):
    """
    This function runs in the background to process a single webhook notification.
    It contains all the original heavy-lifting logic.
    WARNING: Since this is a "fire-and-forget" task, if the server crashes
    while this is running, the task is lost. Robust logging is critical.
    """
    resource = notification.get("resource")
    webhook_logger.info(f"Starting background task for resource: {resource}")

    try:
        ms_user_id, msg_id = extract_ms_ids_from_resource(resource or "")
        if not ms_user_id or not msg_id:
            webhook_logger.warning(f"Could not parse ms_user_id/msg_id from resource: {resource}")
            return

        # 1. Find User
        user_id = await integration_service.get_user_by_ms_id(ms_user_id)
        if not user_id:
            webhook_logger.warning(f"No user_id found for MS Graph ID: {ms_user_id} in integration service.")
            return

        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            webhook_logger.warning(f"No user record found for user_id: {user_id}")
            return
            
        # 2. Check for Duplicates
        already_exists = await db_manager.check_platform_and_message_id_exists('outlook', msg_id, user_id)
        if already_exists:
            webhook_logger.info(f"Outlook message {msg_id} already processed for user {user_id}; skipping task.")
            return

        # 3. Authenticate and Fetch
        user_id_str = str(user_record["_id"])
        outlook = MicrosoftGraphIntegration(user_id_str)
        if not await outlook.authenticate():
            webhook_logger.error(f"Outlook auth failed for user {user_id_str} (ms_id={ms_user_id})")
            return

        normalized = await outlook.normalize_message_for_ingestion(
            user_record=user_record,
            ms_user_id=ms_user_id,
            message_id=msg_id,
            command_prefix="",
        )

        # 4. Insert into Database
        to_insert = {"id": normalized["id"], "normalized": normalized, "user_id": user_id_str}
        inserted_id= await db_manager.insert_new_outlook_email(to_insert)
        inserted_id = inserted_id if inserted_id else None

        if not inserted_id:
            webhook_logger.info(f"Outlook message {msg_id} was processed by another worker; skipping.")
            return

        # 5. Evaluate and Finalize
        normalized["metadata"]["inserted_id"] = inserted_id
        
        praxos_api_key = user_record.get("praxos_api_key")
        praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)
        
        webhook_logger.info(f"Submitting eval event for inserted message {inserted_id}")
        eval_result = await praxos_client.eval_event(normalized, 'outlook')
        webhook_logger.info(f"eval message was: {json.dumps(normalized, indent=2)}")
        webhook_logger.info(f"Eval result for message {inserted_id}: {eval_result}")
        webhook_logger.info(f"Successfully finished background task for resource: {resource}")

    except Exception as e:
        webhook_logger.error(
            f"Background task failed for resource: {resource}",
            exc_info=True  # Provides the full stack trace
        )
        return


# --- Lean Webhook Endpoint ---

@router.post("/outlook", status_code=status.HTTP_202_ACCEPTED)
async def handle_outlook_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handles Outlook webhooks, acknowledging receipt immediately
    and scheduling the actual processing to run in the background.
    """
    # 1. Validation Handshake (no change)
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        webhook_logger.info("Responding to Outlook validation request.")
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    # 2. Receive and Schedule Tasks
    webhook_logger.info("Received Outlook notification webhook. Acknowledging and scheduling tasks.")
    try:
        body = await request.json()
    except json.JSONDecodeError:
        webhook_logger.error("Failed to decode JSON from webhook body.")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    notifications: List[Dict[str, Any]] = body.get("value", [])
    if not notifications:
        webhook_logger.warning("No notifications found in webhook body.")
        return {"status": "accepted", "tasks_scheduled": 0}

    tasks_scheduled = 0
    for notification in notifications:
        # Perform minimal validation before scheduling
        if notification.get("clientState") != settings.OUTLOOK_VALIDATION_TOKEN:
            webhook_logger.warning("Invalid clientState in notification. Ignoring.")
            continue
        if notification.get("changeType") not in ("created", "updated"):
            continue

        # Add the heavy processing function to run in the background
        background_tasks.add_task(process_notification_task, notification)
        tasks_scheduled += 1

    webhook_logger.info(f"Acknowledged receipt. Scheduled {tasks_scheduled} tasks to run in background.")
    return {"status": "accepted", "tasks_scheduled": tasks_scheduled}


# --- Bot Webhook (Unchanged) ---
# This endpoint can remain as is, as it likely handles single, less frequent events.
@router.post("/outlook-bot")
async def handle_outlook_bot_webhook(message: OutlookBotMessage):
    """Handle direct emails sent to the bot's address (e.g., my@praxos.ai)."""
    webhook_logger.info(f"Received bot email from: {message.from_sender.address}")
    webhook_logger.info(f"Message: {json.dumps(message.dict(by_alias=True))}")
    modality_var.set("outlook_bot_webhook")
    sender_email = message.from_sender.address
    user_record = user_service.get_user_by_email(sender_email)
    if not user_record:
        user_integration = await integration_service.get_user_by_integration("email", sender_email)
        if user_integration:
            user_record = user_service.get_user_by_id(user_integration[0])

    if user_record:
        user_id_var.set(str(user_record["_id"]))
        webhook_logger.info(f"Sender {sender_email} is a registered user.")
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
