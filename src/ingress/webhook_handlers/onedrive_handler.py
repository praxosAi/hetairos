from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.config.settings import settings
import json

router = APIRouter()
logger = setup_logger(__name__)

@router.post("/onedrive")
async def handle_onedrive_webhook(request: Request):
    """
    Handles incoming OneDrive webhook notifications.

    Microsoft Graph sends notifications when files/folders change in OneDrive.
    Reference: https://learn.microsoft.com/en-us/onedrive/developer/rest-api/concepts/using-webhooks

    IMPORTANT: OneDrive webhooks only support "updated" changeType.
    No resourceData is included - you must use Delta API to get actual changes.
    """
    try:
        # Handle validation request
        validation_token = request.query_params.get("validationToken")
        if validation_token:
            logger.info("Responding to OneDrive webhook validation request")
            return Response(content=validation_token, media_type="text/plain", status_code=200)

        # Process notification
        body = await request.json()
        logger.info(f"Received OneDrive webhook notification")

        for notification in body.get("value", []):
            # Validate client state
            client_state = notification.get("clientState")
            expected_state = settings.ONEDRIVE_VALIDATION_TOKEN  # From environment

            if client_state != expected_state:
                logger.warning(f"Invalid clientState in OneDrive notification: {client_state}")
                continue

            # Extract notification details
            subscription_id = notification.get("subscriptionId")
            change_type = notification.get("changeType")  # Only "updated" is supported
            resource = notification.get("resource")  # e.g., "me/drive/root"

            logger.info(f"OneDrive change detected: {change_type} on {resource}")

            # Find user by subscription_id
            # Subscription ID is stored in integration.metadata.onedrive_webhook_subscription_id
            user_id = await integration_service.get_user_by_subscription_id(subscription_id, "onedrive")

            if not user_id:
                logger.warning(f"No user found for OneDrive subscription ID: {subscription_id}")
                continue

            user_record = user_service.get_user_by_id(user_id)
            if not user_record:
                logger.error(f"User not found for ID {user_id}")
                continue

            user_id_var.set(str(user_id))
            modality_var.set("onedrive_webhook")

            # IMPORTANT: OneDrive does NOT include file details in webhook
            # You must call Delta API: GET /me/drive/delta to get actual changes
            # Webhook just says "something changed"
            event = {
                "user_id": str(user_id),
                "source": "event_ingestion",
                "payload": {
                    "subscription_id": subscription_id,
                    "change_type": change_type,
                    "resource": resource,
                    "note": "OneDrive webhooks don't include file details - use Delta API"
                },
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'onedrive_webhook'
                },
                "metadata": {
                    'ingest_type': 'onedrive_webhook',
                    'source': 'onedrive',
                    'webhook_event': True,
                    'change_type': change_type,
                    'subscription_id': subscription_id,
                    'requires_delta_sync': True  # Flag to trigger Delta API call
                }
            }

            # await event_queue.publish(event)
            logger.info(f"Processed OneDrive webhook for user {user_id}, change_type: {change_type}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing OneDrive webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
