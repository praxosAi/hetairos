from fastapi import APIRouter, Request, HTTPException
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from src.integrations.imessage.client import IMessageClient
from src.utils.blob_utils import upload_to_blob_storage
import hmac
import hashlib
from src.config.settings import settings
import mimetypes
from bson import ObjectId
from src.utils.database import db_manager

logger = setup_logger(__name__)
router = APIRouter()



@router.post("/imessage")
async def handle_imessage_webhook(request: Request):
    """Handles incoming iMessage updates from Sendblue."""
    body_bytes = await request.body()
    signature = request.headers.get("sb-signing-secret")
    logger.info(f"Received iMessage webhook with signature: {signature}")
    logger.info(f"request is: {request}")
    if settings.SENDBLUE_SIGNING_SECRET and signature != settings.SENDBLUE_SIGNING_SECRET:
        logger.info(f"Invalid signature for iMessage webhook")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"Received data from imessage webhook: {data}")
    
    if data.get("is_outbound") == True:
        return {"status": "ok"}

    phone_number = data.get("from_number")
    if not phone_number:
        logger.warning("No phone number in webhook payload")
        return {"status": "ok"}

    integration_record = await integration_service.is_authorized_user("imessage", phone_number)
    if not integration_record:
        logger.warning(f"User {phone_number} is not authorized to use the bot")
        imessage_client = IMessageClient()
        await imessage_client.send_message(phone_number, "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com")
        return {"status": "ok"}

    user_id = str(integration_record["user_id"])
    text = data.get("content")
    
    if text:
        event = {
            "user_id": user_id,
            'output_type': 'imessage',
            'output_phone_number': phone_number,
            "source": "imessage",
            "payload": {"text": text},
            "metadata": {'message_id': data.get("message_handle"), 'source':'iMessage', 'timestamp': data.get("date_sent")}
        }
        await event_queue.publish(event)

    media_url = data.get("media_url")
    if media_url:
        imessage_client = IMessageClient()
        file_name = media_url.split("/")[-1]
        file_path_local = await imessage_client.download_media_to_temp_path(media_url, file_name)
        
        if file_path_local:
            mime_type = mimetypes.guess_type(file_path_local)[0]
            blob_name = await upload_to_blob_storage(file_path_local, f"{user_id}/imessage/{file_name}")
            
            document_entry = {
                "user_id": ObjectId(user_id),
                "platform_file_id": data.get("message_handle"),
                "platform_message_id": data.get("message_handle"),
                "platform": "imessage",
                'type': 'file',
                "blob_path": blob_name,
                "mime_type": mime_type,
                "caption": "",
                'file_name': file_name
            }
            inserted_id = await db_manager.add_document(document_entry)
            
            event = {
                "user_id": user_id,
                'output_type': 'imessage',
                'output_phone_number': phone_number,
                "source": "imessage",
                "payload": {"files": [{'type': 'file', 'blob_path': blob_name, 'mime_type': mime_type, 'caption': '', 'inserted_id': str(inserted_id)}]},
                "metadata": {'message_id': data.get("message_handle"), 'source':'iMessage', 'timestamp': data.get("date_sent")}
            }
            await event_queue.publish(event)

    return {"status": "ok"}
