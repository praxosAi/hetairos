from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
import hmac
import hashlib
import uuid
import json
import os
from src.utils.logging.webhook_logger import webhook_logger
from src.config.settings import settings
from src.core.event_queue import event_queue
from src.services.user_service import user_service
from src.integrations.whatsapp.client import WhatsAppClient
from src.utils.blob_utils import upload_to_blob_storage, send_to_service_bus
from src.services.integration_service import integration_service
import mimetypes

router = APIRouter()

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify WhatsApp webhook signature"""
    if not signature:
        return False
    expected_signature = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected_signature}", signature)

@router.get("/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """Verify WhatsApp webhook subscription."""
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    webhook_logger.info(f"verify_token: {verify_token}")
    if verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")



@router.post("/whatsapp")
async def handle_whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp messages.
    This endpoint should be fast. It validates the request, normalizes the event,
    and publishes it to a queue for background processing.
    """
    webhook_logger.info("Received WhatsApp webhook")
    body_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_webhook_signature(body_bytes, signature):
        # webhook_logger.error(f"Invalid signature for WhatsApp webhook")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    body = await request.json()
    # webhook_logger.info(f"WhatsApp webhook body: {body}")
    if "entry" in body and body["entry"]:
        for entry in body["entry"]:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" in value:
                    for message in value["messages"]:
                        whatsapp_client = WhatsAppClient()
                        phone_number = message["from"]
                        integration_record = await integration_service.is_authorized_user('whatsapp',phone_number)
                        if not integration_record:
                            webhook_logger.warning(f"Unauthorized user: {phone_number}")
                            ### send a message to the user, informing them that they are not authorized to use the bot.
                            ### @TODO this should really be in egress.
                            await whatsapp_client.send_message(phone_number, "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com")
                            continue


                        webhook_logger.info(f"Marking message as read on webhook with base url {whatsapp_client.base_url}")
                        await whatsapp_client.mark_as_read(message["id"])
                        
                        user_record = user_service.get_user_by_id(integration_record["user_id"])
                        message_type = message.get("type")

                        if message_type == "text":
                            message_text = message.get("text", {}).get("body", "")
                            event = {
                                "user_id": str(user_record["_id"]),
                                'output_type': 'whatsapp',
                                'output_phone_number': phone_number,
                                "source": "whatsapp",
                                "payload": {"text": message_text},
                                "metadata": {"message_id": message["id"],'source':'whatsapp'}
                            }
                            await event_queue.publish(event)
                        
                        elif message_type in ["audio", "voice"]:
                            media_id = message.get(message_type, {}).get("id")
                            if media_id:
                                file_path, _ = await whatsapp_client.download_media_by_id_to_file(media_id)
                                if file_path:
                                    try:
                                        job_id = str(uuid.uuid4())
                                        blob_name = f"{str(user_record['_id'])}/whatsapp/{media_id or job_id}.ogg"
                                        
                                        file_path_blob = await upload_to_blob_storage(file_path, blob_name)
                                        mime_type = mimetypes.guess_type(file_path)
                                        if mime_type[0] is None and ('oga' in file_path or 'ogg' in file_path):
                                            mime_type = ['audio/ogg']

                                        event = {
                                            "user_id": str(user_record["_id"]),
                                            'output_type': 'whatsapp',
                                            'output_phone_number': phone_number,
                                            "source": "whatsapp",
                                            "payload": {"files": [{'type': 'voice', 'blob_path': file_path_blob, 'mime_type': mime_type[0]}]},
                                            "metadata": {"message_id": message["id"],'source':'whatsapp'}
                                        }

                                        await event_queue.publish(event)
                                        webhook_logger.info(f"Queued transcription job {job_id} for user {user_record['_id']}")
                                    finally:
                                        os.unlink(file_path) # Clean up the local file
                        else:
                            webhook_logger.info(f"Unsupported message type: {message_type}")

    return {"status": "ok"}
