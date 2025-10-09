from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
import json

router = APIRouter()
logger = setup_logger(__name__)

@router.post("/google-drive")
async def handle_google_drive_webhook(request: Request):
    """
    Handles incoming Google Drive push notifications.

    Google Drive sends notifications when files change.
    Reference: https://developers.google.com/drive/api/guides/push
    """
    try:
        # Google Drive sends notifications via headers, not body
        resource_id = request.headers.get("x-goog-resource-id")
        resource_state = request.headers.get("x-goog-resource-state")  # "sync", "update", "trash", "change"
        channel_id = request.headers.get("x-goog-channel-id")
        channel_token = request.headers.get("x-goog-channel-token")  # Optional verification token
        changed = request.headers.get("x-goog-changed")  # What changed: "properties", "content", "parents"

        logger.info(f"Received Google Drive webhook - Resource ID: {resource_id}, State: {resource_state}, Changed: {changed}, Channel: {channel_id}")

        # Sync notification is sent when watch is first created - acknowledge it
        if resource_state == "sync":
            logger.info("Received Google Drive sync notification (initial handshake)")
            return {"status": "ok"}

        # No resource ID means invalid notification
        if not resource_id or not channel_id:
            logger.warning("Missing required headers in Google Drive webhook")
            raise HTTPException(status_code=400, detail="Missing required headers")

        # Find user by integration resource_id
        # The resource_id is stored in integration.webhook_info.webhook_resource_id
        user_id = await integration_service.get_user_by_webhook_resource_id(resource_id, "google_drive")

        if not user_id:
            logger.warning(f"No user found for Google Drive resource ID: {resource_id}")
            return {"status": "ok"}  # Return OK to acknowledge webhook

        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            logger.error(f"User not found for ID {user_id}")
            return {"status": "ok"}

        user_id_var.set(str(user_id))
        modality_var.set("google_drive_webhook")

        # Enqueue event for processing
        # The actual file data must be fetched via Google Drive Changes API
        # This webhook just tells us that something changed
        event = {
            "user_id": str(user_id),
            "source": "event_ingestion",
            "payload": {
                "resource_id": resource_id,
                "resource_state": resource_state,
                "channel_id": channel_id,
                "changed": changed
            },
            "logging_context": {
                'user_id': user_id_var.get(),
                'request_id': str(request_id_var.get()),
                'modality': 'google_drive_webhook'
            },
            "metadata": {
                'ingest_type': 'google_drive_webhook',
                'source': 'google_drive',
                'webhook_event': True,
                'resource_state': resource_state,
                'changed': changed
            }
        }

        # await event_queue.publish(event)
        logger.info(f"Processed Google Drive webhook for user {user_id}, resource_state: {resource_state}, changed: {changed}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Google Drive webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
