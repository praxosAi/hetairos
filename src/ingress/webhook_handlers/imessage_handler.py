from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger,user_id_var, modality_var, request_id_var
from src.integrations.imessage.client import IMessageClient
from src.utils.blob_utils import upload_to_blob_storage,upload_bytes_to_blob_storage
from src.utils.audio import caf_bytes_to_ogg_bytes
import hmac
from src.services.engagement_service import research_user_and_engage
import hashlib
from src.config.settings import settings
import mimetypes
from bson import ObjectId
from src.utils.database import db_manager
import requests
from src.services.milestone_service import milestone_service

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
async def handle_imessage_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handles incoming iMessage updates from Sendblue."""
    body_bytes = await request.body()
    signature = request.headers.get("sb-signing-secret")
    logger.info(f"Received iMessage webhook with signature: {signature}")
    modality_var.set("imessage")
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
    imessage_client = IMessageClient()
    text = data.get("content")
    integration_record = await integration_service.is_authorized_user("imessage", phone_number)
    if not integration_record:
        logger.info(f"Authorizing user for phone number {phone_number}")
        try:
            integration_record,user = await integration_service.is_authorizable_user("imessage", phone_number, text)
            if integration_record and user:
                try:
                    user_id_var.set(str(user["_id"]))
                    welcome_message = f"HANDSHAKE ACKNOWLEDGED. \n\niMessage communication initialized. \n\nWelcome to Praxos, {user.get('first_name')}.\nPhone number {phone_number} has been saved. You can now issue orders and communicate with Praxos over iMessage. \n\nRecommended action: Save the following contact card:"
                    await imessage_client.send_message(phone_number, welcome_message)
                    await imessage_client.send_contact_card(phone_number)
                    # welcome_message_2 = "Recommended Action: Ask me what I can do for you."
                    # await imessage_client.send_message(phone_number, welcome_message_2)
                    try:
                        await research_user_and_engage(user,'imessage', phone_number,timestamp = data.get('date_sent'),request_id_var=str(request_id_var.get()))
                    except:
                        logger.error(f"Failed to create research order for new imessage user {user['_id']}")
                except Exception as e:
                    logger.error(f"Failed to send contact card to {phone_number}: {e}")
                integration_record = integration_record
                return {"status": "ok"}
            else:
                logger.warning(f"Unauthorized user: {phone_number}")
                await imessage_client.send_message(phone_number, "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com")
                return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error authorizing user {phone_number}: {e}")
            await imessage_client.send_message(phone_number, "Error authorizing user. Please try again later.")
            return {"status": "ok"}


    user_id = str(integration_record["user_id"])
    user_id_var.set(user_id)
    
    if text:
        event = {
            "user_id": user_id,
            'output_type': 'imessage',
            'output_phone_number': phone_number,
            "source": "imessage",
            "payload": {"text": text},
            "logging_context": {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
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
                "logging_context": {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
                "payload": {"files": [{'type': file_type, 'blob_path': blob_name, 'mime_type': mime_type, 'caption': '', 'inserted_id': str(inserted_id)}]},
                "metadata": {'message_id': data.get("message_handle"), 'source':'iMessage', 'timestamp': data.get("date_sent")}
            }
            await event_queue.publish(event)

    background_tasks.add_task(milestone_service.user_send_message, user_id)
    return {"status": "ok"}
