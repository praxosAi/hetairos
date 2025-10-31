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
                    logger.warning(f"User {message['from']['id']} is not authorized, showing account selection")
                    first_name = message["from"].get("first_name", "")
                    await telegram_client.send_account_selection_prompt(chat_id, first_name)
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

    # Handle callback queries (button clicks)
    if "callback_query" in data:
        callback_query = data["callback_query"]
        callback_data = callback_query["data"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]
        user_from = callback_query["from"]

        username = user_from.get("username", "").lower()
        first_name = user_from.get("first_name", "")
        last_name = user_from.get("last_name", "")

        # Answer the callback to remove loading state
        await telegram_client.answer_callback_query(callback_query["id"])

        if callback_data == "create_account":
            # NEW USER - Show language selection
            await telegram_client.send_language_selection(chat_id, first_name)

        elif callback_data == "link_account":
            # EXISTING USER - Generate linking token and send deep link
            try:
                from src.config.settings import settings
                import httpx

                backend_url = settings.PRAXOS_BASE_URL
                endpoint = f"{backend_url}/api/auth/telegram/generate-link-token"

                payload = {
                    "telegram_chat_id": chat_id,
                    "telegram_username": username,
                    "first_name": first_name,
                    "last_name": last_name
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(endpoint, json=payload, timeout=30)
                    response.raise_for_status()
                    result = response.json()

                link_url = result['data']['link_url']
                expires_in = result['data']['expires_in']

                # Send message with inline button linking to webapp
                link_keyboard = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "🔗 Link My Account",
                                "url": link_url
                            }
                        ]
                    ]
                }

                instructions = f"""To link your existing Praxos account:

                                1. Click the button below to open the webapp
                                2. Make sure you're logged in to your Praxos account
                                3. Confirm the linking

                                ⏱️ This link expires in {expires_in // 60} minutes."""

                await telegram_client.send_message_with_inline_keyboard(
                    chat_id=chat_id,
                    text=instructions,
                    inline_keyboard=link_keyboard
                )

            except Exception as e:
                logger.error(f"Failed to generate link token: {str(e)}")
                error_msg = "Sorry, failed to generate linking URL. Please try again or contact support."
                await telegram_client.send_message(chat_id, error_msg)

        elif callback_data.startswith("lang_"):
            # Language selected - Complete registration
            language = callback_data.split("_")[1]

            from src.services.user_service import user_service

            try:
                registration_result = await user_service.register_telegram_user(
                    telegram_chat_id=chat_id,
                    telegram_username=username,
                    first_name=first_name,
                    last_name=last_name,
                    language=language
                )

                # Welcome messages in each language
                welcome_messages = {
                    "en": f"🎉 Welcome to Praxos, {first_name}!\n\nYour account has been created successfully!\n\nYou can now start chatting with me here. How can I help you today?",
                    "es": f"🎉 ¡Bienvenido a Praxos, {first_name}!\n\n¡Tu cuenta ha sido creada exitosamente!\n\nAhora puedes comenzar a chatear conmigo aquí. ¿Cómo puedo ayudarte hoy?",
                    "pt": f"🎉 Bem-vindo ao Praxos, {first_name}!\n\nSua conta foi criada com sucesso!\n\nVocê já pode começar a conversar comigo aqui. Como posso ajudá-lo hoje?",
                    "ru": f"🎉 Добро пожаловать в Praxos, {first_name}!\n\nВаш аккаунт успешно создан!\n\nТеперь вы можете общаться со мной здесь. Чем могу помочь сегодня?",
                    "fa": f"🎉 به Praxos خوش آمدید، {first_name}!\n\nحساب شما با موفقیت ایجاد شد!\n\nاکنون می‌توانید اینجا با من چت کنید. امروز چطور می‌تونم کمکتون کنم؟",
                    "fr": f"🎉 Bienvenue sur Praxos, {first_name}!\n\nVotre compte a été créé avec succès!\n\nVous pouvez maintenant commencer à discuter avec moi ici. Comment puis-je vous aider aujourd'hui?",
                    "de": f"🎉 Willkommen bei Praxos, {first_name}!\n\nIhr Konto wurde erfolgreich erstellt!\n\nSie können jetzt hier mit mir chatten. Wie kann ich Ihnen heute helfen?",
                    "ar": f"🎉 مرحباً بك في Praxos، {first_name}!\n\nتم إنشاء حسابك بنجاح!\n\nيمكنك الآن بدء الدردشة معي هنا. كيف يمكنني مساعدتك اليوم؟"
                }

                success_msg = welcome_messages.get(language, welcome_messages["en"])

                await telegram_client.send_message(chat_id, success_msg)

                # Trigger first engagement
                from datetime import datetime
                user_record = {"_id": ObjectId(registration_result["user_id"]), "first_name": first_name}
                await research_user_and_engage(
                    user_record,
                    'telegram',
                    chat_id,
                    timestamp=datetime.utcnow(),
                    request_id_var=str(request_id_var.get())
                )

            except Exception as e:
                logger.error(f"Registration failed: {str(e)}")

                # Error messages in each language
                error_messages = {
                    "en": "Sorry, registration failed. Please try again later or contact support.",
                    "es": "Lo sentimos, el registro falló. Por favor, inténtalo de nuevo más tarde o contacta a soporte.",
                    "pt": "Desculpe, o registro falhou. Por favor, tente novamente mais tarde ou entre em contato com o suporte.",
                    "ru": "Извините, регистрация не удалась. Пожалуйста, попробуйте позже или свяжитесь с поддержкой.",
                    "fa": "متاسفیم، ثبت‌نام ناموفق بود. لطفاً بعداً دوباره امتحان کنید یا با پشتیبانی تماس بگیرید.",
                    "fr": "Désolé, l'inscription a échoué. Veuillez réessayer plus tard ou contacter le support.",
                    "de": "Entschuldigung, die Registrierung ist fehlgeschlagen. Bitte versuchen Sie es später erneut oder kontaktieren Sie den Support.",
                    "ar": "عذراً، فشل التسجيل. يرجى المحاولة مرة أخرى لاحقاً أو الاتصال بالدعم."
                }

                error_msg = error_messages.get(language, error_messages["en"])
                await telegram_client.send_message(chat_id, error_msg)

        return {"status": "ok"}

    try:
        if user_id_var.get() != 'SYSTEM_LEVEL':
            background_tasks.add_task(milestone_service.user_send_message, user_id_var.get())
    except Exception as e:
        logger.error(f"Failed to log milestone for user {user_id_var.get()}: {e}")
    return {"status": "ok"}
