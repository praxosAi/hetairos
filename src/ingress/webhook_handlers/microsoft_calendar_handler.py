from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.config.settings import settings
import json

router = APIRouter()
logger = setup_logger(__name__)

@router.post("/microsoft-calendar")
async def handle_microsoft_calendar_webhook(request: Request):
    """
    Handles incoming Microsoft Calendar (Outlook Calendar) webhook notifications.

    Microsoft Graph sends notifications when calendar events change.
    Reference: https://learn.microsoft.com/en-us/graph/webhooks
    """
    try:
        # Handle validation request
        validation_token = request.query_params.get("validationToken")
        if validation_token:
            logger.info("Responding to Microsoft Calendar webhook validation request")
            return Response(content=validation_token, media_type="text/plain", status_code=200)

        # Process notification
        body = await request.json()
        logger.info(f"Received Microsoft Calendar webhook notification")

        for notification in body.get("value", []):
            # Validate client state
            client_state = notification.get("clientState")
            expected_state = settings.CALENDAR_VALIDATION_TOKEN  # From environment

            if client_state != expected_state:
                logger.warning(f"Invalid clientState in Microsoft Calendar notification: {client_state}")
                continue

            # Extract notification details
            subscription_id = notification.get("subscriptionId")
            change_type = notification.get("changeType")  # "created", "updated", "deleted"
            resource = notification.get("resource")  # e.g., "Users/{id}/Events/{id}"

            logger.info(f"Microsoft Calendar event {change_type}: {resource}")

            # Find user by subscription_id
            # Subscription ID is stored in integration.metadata.calendar_webhook_subscription_id
            user_id = await integration_service.get_user_by_subscription_id(subscription_id, "microsoft_calendar")

            if not user_id:
                logger.warning(f"No user found for Microsoft Calendar subscription ID: {subscription_id}")
                continue

            user_record = user_service.get_user_by_id(user_id)
            if not user_record:
                logger.error(f"User not found for ID {user_id}")
                continue

            user_id_var.set(str(user_id))
            modality_var.set("microsoft_calendar_webhook")

            # Note: Microsoft Graph does NOT include resourceData in Calendar webhooks
            # You must call GET /users/{id}/events/{id} to get the actual event data
            event = {
                "user_id": str(user_id),
                "source": "event_ingestion",
                "payload": {
                    "subscription_id": subscription_id,
                    "change_type": change_type,
                    "resource": resource
                },
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'microsoft_calendar_webhook'
                },
                "metadata": {
                    'ingest_type': 'microsoft_calendar_webhook',
                    'source': 'microsoft_calendar',
                    'webhook_event': True,
                    'change_type': change_type,
                    'subscription_id': subscription_id
                }
            }

            # await event_queue.publish(event)
            logger.info(f"Processed Microsoft Calendar webhook for user {user_id}, change_type: {change_type}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Microsoft Calendar webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
