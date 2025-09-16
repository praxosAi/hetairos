from fastapi import APIRouter, Request, HTTPException
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from src.integrations.telegram.client import TelegramClient
from src.utils.blob_utils import upload_to_blob_storage, send_to_service_bus
logger = setup_logger(__name__)
router = APIRouter()
import mimetypes
from bson import ObjectId
from src.utils.database import db_manager
@router.post("/telegram")
async def handle_telegram_webhook(request: Request):
    """Handles incoming Telegram updates."""
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    telegram_client = TelegramClient()
    logger.info(f"Received data from telegram webhook: {data}")
    if "message" in data:
        message = data["message"]

        username = message["from"].get("username", "").lower()
        if not username:
            logger.warning(f"User {message['from']['id']} has no username, cannot authorize")
            await telegram_client.send_message(message["chat"]["id"], "You seem to have not setup a username on telegram yet. this makes it impossible for us to authorize you. Please set a username in your telegram settings, and integrate with praxos.")
            return {"status": "ok"}
        integration_record = await integration_service.is_authorized_user("telegram", username)
        if not integration_record:
            logger.warning(f"User {message['from']['id']} is not authorized to use the bot")
            await telegram_client.send_message(message["chat"]["id"], "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com, and add your telegram username to your account.")
            return {"status": "ok"}
        user_id = str(integration_record["user_id"])
        chat_id = message["chat"]["id"]
        ### for telegram, on the first message, we must store the chat id in the user record.
        if not integration_record.get("telegram_chat_id"):
            integration_record["telegram_chat_id"] = chat_id
            await integration_service.update_integration(integration_record["_id"], integration_record)
        text = message.get("text")
        logger.info(f"Received message from Telegram: {message}")
        #### handling forwarded messages
        forwarded  = False
        forward_origin = {}
        if  message.get("forward_origin"):
            forwarded = True
            forward_origin_raw = message["forward_origin"]
            if forward_origin_raw.get("type") == "hidden_user":
                forward_origin = {"type":"hidden_user",'original_sender_identifier': forward_origin_raw.get("sender_user_name","Unknown"),'forward_date': forward_origin_raw.get("date")}

            elif forward_origin_raw.get("type") == "user":
                sender_user = forward_origin_raw.get("sender_user",{})
                sender_user_full_identifier = ''
                if sender_user.get("first_name"):
                    sender_user_full_identifier += 'First Name:' +  sender_user["first_name"]
                if sender_user.get("last_name"):
                    sender_user_full_identifier += ' Last Name:' +  sender_user["last_name"]
                if sender_user.get("username"):
                    sender_user_full_identifier += ' Username:' +  sender_user["username"]
                forward_origin = {"type":"user",'original_sender_identifier': sender_user_full_identifier,'forward_date': forward_origin_raw.get("date")}
        if text:
            event = {
                "user_id": user_id,
                'output_type': 'telegram',
                'output_chat_id': chat_id,
                "source": "telegram",
                "payload": {"text": text},
                "metadata": {'message_id': message["message_id"],'chat_id': chat_id, 'source':'Telegram','forwarded':forwarded,'forward_origin':forward_origin,'timestamp': message.get("date")}
            }
            await event_queue.publish(event)
        for key in ['video','document','sticker','voice','audio','photo']:
            if not key in message or not message[key]:
                continue
            
            document = message[key]
            file_id = document["file_id"]
            mime_type = document.get("mime_type")
            file_path_data = await telegram_client.get_file_path(file_id)
            file_path = file_path_data["result"]["file_path"]
            file_unique_id = file_path_data["result"]["file_unique_id"]
            caption = message.get("caption","")
            logger.info(f"Received voice message from Telegram: {file_path}")
            file_path_local = await telegram_client.download_file_to_temp_path(file_path, file_unique_id)
            logger.info(f"Downloaded voice message from Telegram: {file_path_local}")
            if not mime_type:
                mime_type = mimetypes.guess_type(file_path_local)
            else:
                mime_type = [mime_type]
            logger.info(f"Mime type of the voice message: {mime_type}")
            if mime_type[0] is None and ('oga' in file_path_local or 'ogg' in file_path_local):
                mime_type = ['audio/ogg']
            blob_name =await upload_to_blob_storage(file_path_local, f"{user_id}/telegram/{file_path_local}")
            file_name_og = document.get("file_name",'Original filename not accessible')
            type_to_use = key
            if key == 'sticker':
                type_to_use = 'image'
            document_entry = {
                "user_id": ObjectId(user_id),
                "platform_file_id": file_unique_id,
                "platform_message_id": chat_id,
                "platform": "telegram",
                'type': type_to_use,
                "blob_path": blob_name,
                "mime_type": mime_type[0],
                "caption": caption,
                'file_name': file_name_og

            }
            inserted_id = await db_manager.add_document(document_entry)
            event = {
                "user_id": user_id,
                'output_type': 'telegram',
                'output_chat_id': chat_id,
                "source": "telegram",
                "payload": {"files": [{'type': type_to_use, 'blob_path': blob_name, 'mime_type': mime_type[0],'caption': caption,'inserted_id': str(inserted_id)}]},
                "metadata": {'message_id': message["message_id"],'chat_id': chat_id,'source':'Telegram', 'forwarded':forwarded,'forward_origin':forward_origin, 'timestamp': message.get("date")}
            }
            await event_queue.publish(event)
    return {"status": "ok"}
