from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
import hmac
import hashlib
import uuid
import json
import os
from src.services.engagement_service import research_user_and_engage
from src.utils.logging.webhook_logger import webhook_logger
from src.config.settings import settings
from src.core.event_queue import event_queue
from src.services.user_service import user_service
from src.integrations.whatsapp.client import WhatsAppClient
from src.utils.blob_utils import upload_to_blob_storage
from src.services.integration_service import integration_service
from src.utils.database import db_manager
import mimetypes
from bson import ObjectId
from src.utils.logging.base_logger import user_id_var, modality_var, request_id_var

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
    modality_var.set('whatsapp')
    if not verify_webhook_signature(body_bytes, signature):
        # webhook_logger.error(f"Invalid signature for WhatsApp webhook")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    try:
        body = json.loads(body_bytes)
        webhook_logger.info(f"WhatsApp webhook body: {body}")
    except json.JSONDecodeError:
        webhook_logger.error("Failed to decode webhook body as JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    webhook_logger.info(f"WhatsApp webhook body: {body}")
    if "entry" in body and body["entry"]:
        for entry in body["entry"]:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" in value:
                    for message in value["messages"]:
                        whatsapp_client = WhatsAppClient()
                        phone_number = message["from"]
                        message_text = message.get("text", {}).get("body", "")
                        integration_record = await integration_service.is_authorized_user('whatsapp',phone_number)
                        if not integration_record:
                            ## try to authorize with code:
                            try:
                                integration_record_new,user_record = await integration_service.is_authorizable_user('whatsapp',phone_number,message_text)
                                if integration_record_new and user_record:
                                    user_id_var.set(str(user_record["_id"]))
                                    webhook_logger.info(f"Authorized new user for whatsapp with phone number {phone_number}")
                                    welcome_message = f"HANDSHAKE ACKNOWLEDGED. \n\nWhatsapp Connection Initialized. \n\nWelcome to Praxos, {user_record.get('first_name')}.\n\nPhone number {phone_number} has been saved. You can now issue orders and communicate with Praxos over WhatsApp. \n\nRecommended action: Save the following contact card:"
                                    await whatsapp_client.send_message(phone_number, welcome_message)
                                    try:
                                        await whatsapp_client.send_praxos_contact_card(phone_number)
                                    except Exception as e:
                                        webhook_logger.error(f"Failed to send contact card to {phone_number}: {e}")
                                    
                                    integration_record = integration_record_new
                                    try:
                                        await research_user_and_engage(user_record,'whatsapp', phone_number,timestamp = message.get('timestamp'),request_id_var=str(request_id_var.get()))
                                    except:
                                        webhook_logger.error(f"Failed to create research order for new whatsapp user {user_record['_id']}")
                                    return
                                else:
                                    webhook_logger.warning(f"Unauthorized user: {phone_number}")
                                    await whatsapp_client.send_message(phone_number, "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com")
                                    return
                            except Exception as e:
                                webhook_logger.error(f"Error during authorization attempt for {phone_number}: {e}")
                                await whatsapp_client.send_message(phone_number, "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com. if this message seems to be an error, please contact support on discord.")
                                return

                        webhook_logger.info(f"Marking message as read on webhook with base url {whatsapp_client.base_url}")
                        await whatsapp_client.mark_as_read(message["id"])
                        ### check if message is forwarded.
                        forwarded = message.get("context",{}).get("forwarded",False) or message.get("context",{}).get("frequently_forwarded",False)


                        user_record = user_service.get_user_by_id(integration_record["user_id"])

                        message_type = message.get("type")
                        user_id_var.set(str(user_record["_id"]))
                        if message_type == "text":
                            message_text = message.get("text", {}).get("body", "")
                            event = {
                                "user_id": str(user_record["_id"]),
                                'output_type': 'whatsapp',
                                'output_phone_number': phone_number,
                                "source": "whatsapp",
                                "payload": {"text": message_text},
                                "logging_context": {'user_id': str(user_record["_id"]), 'request_id': str(request_id_var.get()), 'modality': modality_var.get() },
                                "metadata": {"message_id": message["id"],'source':'whatsapp','forwarded':forwarded, 'timestamp': message.get('timestamp')}
                            }
                            await event_queue.publish(event)
                        
                        elif message_type in ["audio", "voice","document",'image','video']:
                            media_id = message.get(message_type, {}).get("id")
                            if media_id:
                                mime_type = [message.get(message_type, {}).get("mime_type").split(';')[0]]
                                extension = mimetypes.guess_extension(mime_type[0]) or ''
                                webhook_logger.info(f"Downloading media {media_id} of type {message_type} with extension {extension} and mime type {mime_type} for user {user_record['_id']}")
                                file_path, _ = await whatsapp_client.download_media_by_id_to_file(media_id,extension)
                                if file_path:
                                    try:
                                        job_id = str(uuid.uuid4())

                                        blob_name = f"{str(user_record['_id'])}/whatsapp/{media_id or job_id}.{extension.lstrip('.')}"
                                        caption = message.get(message_type, {}).get("caption", "")

                                        # Upload images to CDN container, other files to default container
                                        if message_type == 'image':
                                            file_path_blob = await upload_to_blob_storage(file_path, blob_name, container_name="cdn-container")
                                        else:
                                            file_path_blob = await upload_to_blob_storage(file_path, blob_name)
                                        document_entry = {
                                            "user_id": ObjectId(user_record["_id"]),
                                            "platform_file_id": media_id,
                                            "platform_message_id": message["id"],
                                            "platform": "whatsapp",
                                            'type': message_type,
                                            "blob_path": blob_name,
                                            "mime_type": mime_type[0],
                                            "caption": caption,
                                            "file_name": 'whatsapp files do not have original file names'

                                        }
                                        inserted_id = await db_manager.add_document(document_entry)
                                        event = {
                                            "user_id": str(user_record["_id"]),
                                            'output_type': 'whatsapp',
                                            'output_phone_number': phone_number,
                                            "source": "whatsapp",
                                            "logging_context": {'user_id': str(user_record["_id"]), 'request_id': str(request_id_var.get()), 'modality': modality_var.get() },

                                            "payload": {"files": [{'type': message_type, 'blob_path': file_path_blob, 'mime_type': mime_type[0],'caption': caption,'inserted_id': str(inserted_id)}]},
                                            "metadata": {"message_id": message["id"],'source':'whatsapp','forwarded':forwarded,'timestamp': message.get('timestamp')}
                                        }


                                        await event_queue.publish(event)
                                        
                                        webhook_logger.info(f"Queued transcription job {job_id} for user {user_record['_id']}")
                                    finally:
                                        os.unlink(file_path) # Clean up the local file


    return {"status": "ok"}
