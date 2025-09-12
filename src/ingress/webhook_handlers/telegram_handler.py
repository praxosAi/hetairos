from fastapi import APIRouter, Request, HTTPException
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from src.integrations.telegram.client import TelegramClient
from src.utils.blob_utils import upload_to_blob_storage, send_to_service_bus
logger = setup_logger(__name__)
router = APIRouter()
import mimetypes

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
        username = message["from"]["username"].lower()
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
        print(f"Received message from Telegram: {message}")
        if text:
            event = {
                "user_id": user_id,
                'output_type': 'telegram',
                'output_chat_id': chat_id,
                "source": "telegram",
                "payload": {"text": text},
                "metadata": {'message_id': message["message_id"],'chat_id': chat_id, 'source':'Telegram'}
            }
            await event_queue.publish(event)
        if 'voice' in message and message["voice"]:
            voice = message["voice"]
            file_id = voice["file_id"]
            file_path_data = await telegram_client.get_file_path(file_id)
            file_path = file_path_data["result"]["file_path"]
            file_unique_id = file_path_data["result"]["file_unique_id"]
            logger.info(f"Received voice message from Telegram: {file_path}")
            file_path_local = await telegram_client.download_file_to_temp_path(file_path, file_unique_id)
            logger.info(f"Downloaded voice message from Telegram: {file_path_local}")
            mime_type = mimetypes.guess_type(file_path_local)
            logger.info(f"Mime type of the voice message: {mime_type}")
            if mime_type[0] is None and ('oga' in file_path_local or 'ogg' in file_path_local):
                mime_type = ['audio/ogg']
            blob_name =await upload_to_blob_storage(file_path_local, f"{user_id}/telegram/{file_path_local}")
            event = {
                "user_id": user_id,
                'output_type': 'telegram',
                'output_chat_id': chat_id,
                "source": "telegram",
                "payload": {"files": [{'type': 'voice', 'blob_path': blob_name, 'mime_type': mime_type[0]}]},
                "metadata": {'message_id': message["message_id"],'chat_id': chat_id,'source':'Telegram'}
            }
            await event_queue.publish(event)
        for key in ['video','document','sticker']:
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
            event = {
                "user_id": user_id,
                'output_type': 'telegram',
                'output_chat_id': chat_id,
                "source": "telegram",
                "payload": {"files": [{'type': key, 'blob_path': blob_name, 'mime_type': mime_type[0],'caption': caption}]},
                "metadata": {'message_id': message["message_id"],'chat_id': chat_id,'source':'Telegram'}
            }
            await event_queue.publish(event)
    return {"status": "ok"}
