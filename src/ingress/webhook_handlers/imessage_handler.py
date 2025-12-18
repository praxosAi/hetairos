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
import re
from src.utils.file_manager import file_manager

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
                await imessage_client.send_message(phone_number, f"This number is not authorized to use this bot. Please register with myPraxos on https://app.mypraxos.com/integrations?auto-connect=true&provider=imessage&phone_number={phone_number.replace('+','%2B')}")
                return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error authorizing user {phone_number}: {e}")
            await imessage_client.send_message(phone_number, "Error authorizing user. Please try again later.")
            return {"status": "ok"}


    user_id = str(integration_record["user_id"])
    user_id_var.set(user_id)

    # Check if text contains Apple Maps location URL
    is_location = False
    if text:
        # Pattern to match Apple Maps URLs with coordinates
        location_pattern = r'https?://maps\.apple\.com/\?ll=(-?\d+\.\d+),(-?\d+\.\d+)'
        location_match = re.search(location_pattern, text)

        if location_match:
            is_location = True
            latitude = float(location_match.group(1))
            longitude = float(location_match.group(2))

            # Try to extract location name from query parameter
            location_name = None
            name_pattern = r'[&?]q=([^&]+)'
            name_match = re.search(name_pattern, text)
            if name_match:
                import urllib.parse
                location_name = urllib.parse.unquote(name_match.group(1))

            logger.info(f"Received location from iMessage user {user_id}: lat={latitude}, lng={longitude}, name={location_name}")

            # Store location in user preferences
            from src.services.user_service import user_service
            try:
                user_service.save_user_location(
                    user_id=user_id,
                    latitude=latitude,
                    longitude=longitude,
                    platform="imessage",
                    location_name=location_name
                )
                logger.info(f"Saved location for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to save location for user {user_id}: {e}")

            # Create event for location
            location_text = f"User shared location: {latitude}, {longitude}"
            if location_name:
                location_text += f" ({location_name})"

            event = {
                "user_id": user_id,
                'output_type': 'imessage',
                'output_phone_number': phone_number,
                "source": "imessage",
                "logging_context": {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
                "payload": {"text": location_text},
                "metadata": {
                    'message_id': data.get("message_handle"),
                    'source': 'iMessage',
                    'timestamp': data.get("date_sent"),
                    'type': 'text',
                    'location': {
                        "latitude": latitude,
                        "longitude": longitude,
                        "name": location_name
                    }
                }
            }
            await event_queue.publish(event)

    # Handle regular text messages (if not a location)
    if text and not is_location:
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
        # Skip .pluginPayloadAttachment files (these are iMessage's internal location data)
        if media_url.endswith('.pluginPayloadAttachment'):
            logger.info(f"Skipping .pluginPayloadAttachment file (location data already processed)")
        else:
            imessage_client = IMessageClient()
            file_name = media_url.split("/")[-1]
            file_bytes = requests.get(media_url).content

            if file_bytes:
                try:
                    mime_type = mimetypes.guess_type(file_name)[0]

                    # Special handling for CAF audio (iMessage-specific)
                    if file_name.endswith('.caf'):
                        logger.info(f"Converting CAF audio to OGG for {file_name}")
                        file_bytes = caf_bytes_to_ogg_bytes(file_bytes)
                        file_name = file_name.replace('.caf', '.ogg')
                        mime_type = 'audio/ogg'

                    # Detect platform_type from extension (using old mapping for compatibility)
                    extension = '.' + file_name.split('.')[-1].lower()
                    platform_type = extensions_to_filetypes.get(extension, 'document')

                    # Use FileManager for unified file handling
                    file_result = await file_manager.receive_file(
                        user_id=user_id,
                        platform="imessage",
                        file_bytes=file_bytes,  # Already in memory from HTTP GET
                        filename=file_name,
                        mime_type=mime_type,
                        caption="",
                        platform_file_id=data.get("message_handle"),
                        platform_message_id=data.get("message_handle"),
                        platform_type=platform_type,  # iMessage type hint (image, video, audio, document)
                        conversation_id=None,  # Not known at webhook time
                        auto_add_to_media_bus=False,  # Will be added later when conversation starts
                        auto_cleanup=False  # No temp file to cleanup (file_bytes, not file_path)
                    )

                    # Publish event with FileResult
                    event = {
                        "user_id": user_id,
                        'output_type': 'imessage',
                        'output_phone_number': phone_number,
                        "source": "imessage",
                        "logging_context": {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
                        "payload": {"files": [file_result.to_event_file_entry()]},
                        "metadata": {
                            'message_id': data.get("message_handle"),
                            'source': 'iMessage',
                            'timestamp': data.get("date_sent")
                        }
                    }
                    await event_queue.publish(event)
                    logger.info(f"Published event for file: {file_result.file_name} (type: {file_result.file_type})")

                except Exception as e:
                    logger.error(f"Failed to process iMessage file {file_name}: {e}", exc_info=True)

    try:
        if user_id_var.get() != 'SYSTEM_LEVEL':
            background_tasks.add_task(milestone_service.user_send_message, user_id_var.get())
    except Exception as e:
        logger.error(f"Failed to log milestone for user {user_id_var.get()}: {e}")
    return {"status": "ok"}
