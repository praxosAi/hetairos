from fastapi import APIRouter, Request, HTTPException
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.integrations.telegram.client import TelegramClient
from src.utils.blob_utils import upload_to_blob_storage
from src.services.engagement_service import research_user_and_engage
logger = setup_logger(__name__)
router = APIRouter()
import mimetypes
from bson import ObjectId
from src.utils.database import db_manager
@router.post("/telegram")
async def handle_telegram_webhook(request: Request):
    """Handles incoming Telegram updates."""
    modality_var.set("telegram")
    try:
        data = await request.json()
    except Exception as e:
        logger.info(f"Invalid JSON in Telegram webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    telegram_client = TelegramClient()
    logger.info(f"Received data from telegram webhook: {data}")
    if "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        username = message["from"].get("username", "").lower()
        modality_var.set("telegram")
        if username:
            integration_record = await integration_service.is_authorized_user("telegram", username)
        else:
            username = 'NOT_SETUP'
            integration_record = await integration_service.is_authorized_user_telegram_chat_id(chat_id)
        if not integration_record:
            logger.info(f"User {username} not authorized, attempting to authorize.")
            try:
                message_text = message.get("text","")
                integration_record_new,user_record = await integration_service.is_authorizable_user('telegram',username, message_text, chat_id)
                if integration_record_new and user_record:
                    user_id_var.set(str(user_record["_id"]))
                    try:
                        welcome_message = f"HANDSHAKE ACKNOWLEDGED. \n\nTelegram communication initialized. \n\nWelcome to Praxos, {user_record.get('first_name')}.\nUser name @{username} has been saved. You can now issue orders and communicate with Praxos over Telegram."
                        await telegram_client.send_message(message["chat"]["id"], welcome_message)
                        try:
                            await research_user_and_engage(user_record,'telegram', chat_id,timestamp = message.get('date'),request_id_var=str(request_id_var.get()))
                        except:
                            logger.error(f"Failed to create research order for new telegram user {user_record['_id']}")
                        return {"status": "ok"}
                    except Exception as e:
                        logger.error(f"Failed to send welcome message to {username}: {e}")
                    integration_record = integration_record_new
                    return
                else:
                    logger.warning(f"User {message['from']['id']} is not authorized to use the bot")
                    await telegram_client.send_message(message["chat"]["id"], "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com, and add your telegram username to your account.")
                    return {"status": "ok"}
            except Exception as e:
                logger.error(f"Error during authorization attempt for {username}: {e}")
                await telegram_client.send_message(message["chat"]["id"], "You are not authorized to use this bot. Please register with Praxos on www.mypraxos.com, and add your telegram username to your account. if this message seems to be an error, please contact support on discord.")
                return {"status": "ok"}
        user_id = str(integration_record["user_id"])

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
                'logging_context': {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get() },
                "payload": {"text": text},
                "metadata": {'message_id': message["message_id"],'chat_id': chat_id, 'source':'Telegram','forwarded':forwarded,'forward_origin':forward_origin,'timestamp': message.get("date")}
            }
            await event_queue.publish(event)
        for key in ['video','document','sticker','voice','audio','photo','image']:
            if not key in message or not message[key]:
                continue
            
            documents = message[key]
            if isinstance(documents, dict):
                documents = [documents]
            if key in ['photo','image','sticker'] and len(documents) > 1:
                documents = [documents[-1]]  # Get the highest resolution photo only
            for document in documents:
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
                # Upload images to CDN container, everything else to default container
                if key in ['sticker','photo']:
                    blob_name = await upload_to_blob_storage(file_path_local, f"{user_id}/telegram/{file_path_local}", container_name="cdn-container")
                    type_to_use = 'image'
                else:
                    blob_name = await upload_to_blob_storage(file_path_local, f"{user_id}/telegram/{file_path_local}")
                    type_to_use = key

                file_name_og = document.get("file_name",'Original filename not accessible')
                
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
                    'logging_context': {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get() },
                    "source": "telegram",
                    "payload": {"files": [{'type': type_to_use, 'blob_path': blob_name, 'mime_type': mime_type[0],'caption': caption,'inserted_id': str(inserted_id)}]},
                    "metadata": {'message_id': message["message_id"],'chat_id': chat_id,'source':'Telegram', 'forwarded':forwarded,'forward_origin':forward_origin, 'timestamp': message.get("date")}
                }
                await event_queue.publish(event)
    return {"status": "ok"}
