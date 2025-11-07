from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger, modality_var, user_id_var, request_id_var
from src.services.milestone_service import milestone_service

logger = setup_logger(__name__)
router = APIRouter()


@router.post("/ios")
async def handle_ios_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handles incoming iOS Shortcuts webhook updates.

    Expected data format:
    {
        "number": "+1 (917) 763-2726",  # Sender's phone number
        "phone": "+1 (917) 763-2726",   # Alternate format
        "msg": "Message content",
        "recepient": "Device-Name",      # iOS device name
        "contact": "Contact Name"        # Sender's contact name
    }

    Auth: Token in query params (/webhooks/ios?token=abc123)
    """
    modality_var.set("ios")

    # Extract token from query params
    token = request.query_params.get("token")
    if not token:
        logger.warning("No token provided in iOS webhook request")
        raise HTTPException(status_code=401, detail="Missing authentication token")

    # Parse JSON body
    try:
        data = await request.json()
    except Exception as e:
        logger.info(f"Invalid JSON in iOS webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"Received data from iOS webhook with token: {token[:8]}...")

    # Get sender's phone number (try both fields)
    sender_phone = data.get("number") or data.get("phone")
    if not sender_phone:
        logger.warning("No sender phone number in iOS webhook payload")
        return {"status": "ok"}

    # Get message content
    message_text = data.get("msg", "")
    if not message_text:
        logger.warning("Empty message in iOS webhook payload")
        return {"status": "ok"}

    # Look up user integration by token
    integration_record = await integration_service.get_integration_by_ios_token(token)

    if not integration_record:
        logger.warning(f"No user found for iOS token: {token[:8]}...")
        raise HTTPException(status_code=403, detail="Invalid token")

    user_id = str(integration_record["user_id"])
    user_id_var.set(user_id)

    logger.info(f"iOS webhook authorized for user {user_id}, sender: {sender_phone}")

    # Create event for the incoming message
    event = {
        "user_id": user_id,
        'output_type': 'ios',
        "source": "ios",
        "payload": {"text": message_text},
        "logging_context": {
            'user_id': user_id,
            'request_id': str(request_id_var.get()),
            'modality': modality_var.get()
        },
        "metadata": {
            'source': 'iOS Shortcuts',
            'sender_phone': sender_phone,
            'contact_name': data.get("contact"),
            'device_name': data.get("recepient"),
            'timestamp': None  # iOS Shortcuts doesn't provide timestamp
        }
    }

    # Store the sender's phone number for responses (if not already stored)
    if not integration_record.get("ios_user_phone"):
        # This is the first message - store the user's phone number
        # We'll use this to send commands back via iMessage
        await integration_service.update_ios_user_phone(str(integration_record["_id"]), sender_phone)
        logger.info(f"Stored user phone number {sender_phone} for iOS integration")

    await event_queue.publish(event)
    logger.info(f"Published iOS event for user {user_id} from sender {sender_phone}")

    # Log milestone
    try:
        if user_id_var.get() != 'SYSTEM_LEVEL':
            background_tasks.add_task(milestone_service.user_send_message, user_id_var.get())
    except Exception as e:
        logger.error(f"Failed to log milestone for user {user_id_var.get()}: {e}")

    return {"status": "ok"}
