from fastapi import APIRouter, Request, HTTPException
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from src.integrations.imessage.client import IMessageClient
from src.utils.blob_utils import upload_to_blob_storage,upload_bytes_to_blob_storage
from src.utils.audio import caf_bytes_to_ogg_bytes
import hmac
import hashlib
from src.config.settings import settings
import mimetypes
from bson import ObjectId
from src.utils.database import db_manager
import requests
logger = setup_logger(__name__)
router = APIRouter()

extensions_to_filetypes = {
    '.jpg': 'image',
    '.jpeg': 'image',
    '.png': 'image',
    '.gif': 'image',
    '.mp4': 'video',
    '.mov': 'video',
    '.pdf': 'document',
    '.doc': 'document',
    '.docx': 'document',
    '.xls': 'document',
    '.xlsx': 'document',
    '.ppt': 'document',
    '.pptx': 'document',
    '.txt': 'document',
    '.mp3': 'audio',
    '.wav': 'audio',
    '.caf': 'audio',
    '.ogg': 'audio',
    '.m4a': 'audio',
}


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
        file_bytes = requests.get(media_url).content
        
        if file_bytes:
            mime_type = mimetypes.guess_type(file_name)[0]
            if file_name.endswith('.caf'):
                file_bytes = caf_bytes_to_ogg_bytes(file_bytes)
                file_name = file_name.replace('.caf', '.ogg')
                mime_type = 'audio/ogg'
            blob_name = await upload_bytes_to_blob_storage(file_bytes, f"{user_id}/imessage/{file_name}"    , content_type=mime_type)
            ### we need to convert the file
            file_type = extensions_to_filetypes.get('.' + file_name.split('.')[-1].lower(), 'document')
            document_entry = {
                "user_id": ObjectId(user_id),
                "platform_file_id": data.get("message_handle"),
                "platform_message_id": data.get("message_handle"),
                "platform": "imessage",
                'type': file_type,
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
                "payload": {"files": [{'type': file_type, 'blob_path': blob_name, 'mime_type': mime_type, 'caption': '', 'inserted_id': str(inserted_id)}]},
                "metadata": {'message_id': data.get("message_handle"), 'source':'iMessage', 'timestamp': data.get("date_sent")}
            }
            await event_queue.publish(event)

    return {"status": "ok"}
