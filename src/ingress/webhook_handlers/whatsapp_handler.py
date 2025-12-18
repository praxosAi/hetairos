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
from src.services.milestone_service import milestone_service
from src.utils.file_manager import file_manager

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
                                    await whatsapp_client.send_message(phone_number, f"This number is not authorized to use this bot. Please register with myPraxos on https://app.mypraxos.com/integrations?auto-connect=true&provider=imessage&phone_number={phone_number.replace('+','%2B')}")
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
                        if not user_record:
                            webhook_logger.error(f"User record not found for integration {integration_record['_id']}")
                            return
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
                                mime_type_raw = message.get(message_type, {}).get("mime_type", "").split(';')[0]
                                extension = mimetypes.guess_extension(mime_type_raw) or ''
                                webhook_logger.info(f"Downloading media {media_id} of type {message_type} with extension {extension} and mime type {mime_type_raw} for user {user_record['_id']}")
                                file_path, _ = await whatsapp_client.download_media_by_id_to_file(media_id, extension)
                                if file_path:
                                    try:
                                        caption = message.get(message_type, {}).get("caption", "")

                                        # WhatsApp doesn't provide original filenames - generate one
                                        filename = file_manager.generate_filename(
                                            platform="whatsapp",
                                            platform_file_id=media_id,
                                            extension=extension,
                                            mime_type=mime_type_raw
                                        )

                                        # Use FileManager for unified file handling
                                        file_result = await file_manager.receive_file(
                                            user_id=str(user_record["_id"]),
                                            platform="whatsapp",
                                            file_path=file_path,
                                            filename=filename,
                                            mime_type=mime_type_raw,
                                            caption=caption,
                                            platform_file_id=media_id,
                                            platform_message_id=message["id"],
                                            platform_type=message_type,  # WhatsApp type hint (audio, voice, document, image, video)
                                            conversation_id=None,  # Not known at webhook time
                                            auto_add_to_media_bus=False,  # Will be added later when conversation starts
                                            auto_cleanup=True  # FileManager will clean up temp file
                                        )

                                        # Publish event with FileResult
                                        event = {
                                            "user_id": str(user_record["_id"]),
                                            'output_type': 'whatsapp',
                                            'output_phone_number': phone_number,
                                            "source": "whatsapp",
                                            "logging_context": {'user_id': str(user_record["_id"]), 'request_id': str(request_id_var.get()), 'modality': modality_var.get() },
                                            "payload": {"files": [file_result.to_event_file_entry()]},
                                            "metadata": {
                                                "message_id": message["id"],
                                                'source': 'whatsapp',
                                                'forwarded': forwarded,
                                                'timestamp': message.get('timestamp')
                                            }
                                        }

                                        await event_queue.publish(event)
                                        webhook_logger.info(f"Published event for file: {file_result.file_name} (type: {file_result.file_type})")

                                    except Exception as e:
                                        webhook_logger.error(f"Failed to process WhatsApp file {media_id}: {e}", exc_info=True)

                        elif message_type == "location":
                            location_data = message.get("location", {})
                            latitude = location_data.get("latitude")
                            longitude = location_data.get("longitude")
                            location_name = location_data.get("name")
                            location_address = location_data.get("address")

                            webhook_logger.info(f"Received location from WhatsApp user {user_record['_id']}: lat={latitude}, lng={longitude}")

                            # Store location in user preferences
                            try:
                                user_service.save_user_location(
                                    user_id=str(user_record["_id"]),
                                    latitude=latitude,
                                    longitude=longitude,
                                    platform="whatsapp",
                                    location_name=location_name
                                )
                                webhook_logger.info(f"Saved location for user {user_record['_id']}")
                            except Exception as e:
                                webhook_logger.error(f"Failed to save location for user {user_record['_id']}: {e}")

                            # Create event for location
                            location_text = f"User shared location: {latitude}, {longitude}"
                            if location_name:
                                location_text += f" ({location_name})"
                            if location_address:
                                location_text += f" - {location_address}"

                            event = {
                                "user_id": str(user_record["_id"]),
                                'output_type': 'whatsapp',
                                'output_phone_number': phone_number,
                                "source": "whatsapp",
                                "logging_context": {'user_id': str(user_record["_id"]), 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
                                "payload": {"text": location_text},
                                "metadata": {
                                    "message_id": message["id"],
                                    'source': 'whatsapp',
                                    'timestamp': message.get('timestamp'),
                                    'type': 'text',
                                    'location': {
                                        "latitude": latitude,
                                        "longitude": longitude,
                                        "name": location_name,
                                        "address": location_address
                                    }
                                }
                            }
                            await event_queue.publish(event)

                        try:
                            if user_id_var.get() != 'SYSTEM_LEVEL':
                                background_tasks.add_task(milestone_service.user_send_message, user_id_var.get())
                        except Exception as e:
                            webhook_logger.error(f"Failed to log milestone for user {user_record['_id']}: {e}")
    return {"status": "ok"}
