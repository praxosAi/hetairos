from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.integrations.telegram.client import TelegramClient
from src.utils.blob_utils import upload_to_blob_storage
from src.services.engagement_service import research_user_and_engage
import mimetypes
from bson import ObjectId
import os
from src.utils.database import db_manager
from src.services.milestone_service import milestone_service
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp
from src.utils.file_manager import file_manager

logger = setup_logger(__name__)
router = APIRouter()

# Initialize scheduler for telegram webhook management
telegram_scheduler = AsyncIOScheduler()

async def set_telegram_webhook():
    """Set Telegram webhook URL. Called periodically to ensure webhook is registered."""
    from src.config.settings import settings

    token = settings.TELEGRAM_BOT_TOKEN
    webhook_url = "https://hooks.praxos.ai/webhooks/telegram"
    if os.getenv("ENV_NAME","production") == "test":
        webhook_url = "https://hooks.praxos.ai/test/webhooks/telegram"
    url = f"https://api.telegram.org/bot{token}/setWebhook"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"url": webhook_url}) as response:
                result = await response.json()
                if result.get("ok"):
                    logger.info(f"Telegram webhook set successfully: {webhook_url}")
                else:
                    logger.error(f"Failed to set Telegram webhook: {result}")
    except Exception as e:
        logger.error(f"Error setting Telegram webhook: {e}")
@router.post("/telegram")
async def handle_telegram_webhook(request: Request, background_tasks: BackgroundTasks):
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
                "metadata": {'message_id': message["message_id"],'chat_id': chat_id, 'source':'telegram','forwarded':forwarded,'forward_origin':forward_origin,'timestamp': message.get("date")}
            }
            await event_queue.publish(event)

        # Handle location messages
        if "location" in message:
            location = message["location"]
            latitude = location.get("latitude")
            longitude = location.get("longitude")
            horizontal_accuracy = location.get("horizontal_accuracy")

            logger.info(f"Received location from Telegram user {user_id}: lat={latitude}, lng={longitude}")

            # Store location in user preferences
            from src.services.user_service import user_service
            try:
                user_service.save_user_location(
                    user_id=user_id,
                    latitude=latitude,
                    longitude=longitude,
                    platform="telegram"
                )
                logger.info(f"Saved location for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to save location for user {user_id}: {e}")

            # Create event for location
            location_text = f"User shared location: {latitude}, {longitude}"
            if horizontal_accuracy:
                location_text += f" (accuracy: {horizontal_accuracy}m)"

            event = {
                "user_id": user_id,
                'output_type': 'telegram',
                'output_chat_id': chat_id,
                "source": "telegram",
                'logging_context': {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
                "payload": {"text": location_text},
                "metadata": {
                    'message_id': message["message_id"],
                    'chat_id': chat_id,
                    'source': 'telegram',
                    'timestamp': message.get("date"),
                    'type': 'text',
                    'location': {
                        "latitude": latitude,
                        "longitude": longitude,
                        "accuracy": horizontal_accuracy
                    }
                }
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
                logger.info(f"Received file from Telegram: {file_path}")
                file_path_local = await telegram_client.download_file_to_temp_path(file_path, file_unique_id)
                logger.info(f"Downloaded file from Telegram: {file_path_local}")

                # Get MIME type
                if not mime_type:
                    mime_type_tuple = mimetypes.guess_type(file_path_local)
                    mime_type = mime_type_tuple[0] if mime_type_tuple else None

                # Special handling for OGG audio
                if mime_type is None and ('oga' in file_path_local or 'ogg' in file_path_local):
                    mime_type = 'audio/ogg'

                # Get original filename
                file_name_og = document.get("file_name", f"telegram_{file_unique_id}")

                # Use FileManager for unified file handling
                try:
                    file_result = await file_manager.receive_file(
                        user_id=user_id,
                        platform="telegram",
                        file_path=file_path_local,
                        filename=file_name_og,
                        mime_type=mime_type,
                        caption=caption,
                        platform_file_id=file_unique_id,
                        platform_message_id=str(chat_id),
                        platform_type=key,  # Telegram type hint (photo, voice, video, etc.)
                        conversation_id=None,  # Not known at webhook time
                        auto_add_to_media_bus=False,  # Will be added later when conversation starts
                        auto_cleanup=True  # FileManager will clean up temp file
                    )

                    # Publish event with FileResult
                    event = {
                        "user_id": user_id,
                        'output_type': 'telegram',
                        'output_chat_id': chat_id,
                        'logging_context': {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get() },
                        "source": "telegram",
                        "payload": {"files": [file_result.to_event_file_entry()]},
                        "metadata": {
                            'message_id': message["message_id"],
                            'chat_id': chat_id,
                            'source': 'telegram',
                            'forwarded': forwarded,
                            'forward_origin': forward_origin,
                            'timestamp': message.get("date")
                        }
                    }
                    await event_queue.publish(event)
                    logger.info(f"Published event for file: {file_result.file_name} (type: {file_result.file_type})")

                except Exception as e:
                    logger.error(f"Failed to process file {file_name_og}: {e}", exc_info=True)
    try:
        if user_id_var.get() != 'SYSTEM_LEVEL':
            background_tasks.add_task(milestone_service.user_send_message, user_id_var.get())
    except Exception as e:
        logger.error(f"Failed to log milestone for user {user_id_var.get()}: {e}")
    return {"status": "ok"}
