from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.config.settings import settings
from src.core.praxos_client import PraxosClient
from src.utils.database import db_manager
from datetime import datetime, timezone
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

            # Build notification data for trigger evaluation
            notification_data = {
                "subscription_id": subscription_id,
                "change_type": change_type,
                "resource": resource,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "OneDrive webhooks don't include file details - use Delta API"
            }

            # Evaluate triggers
            praxos_api_key = user_record.get("praxos_api_key")
            praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

            logger.info(f"Evaluating triggers for OneDrive notification")
            event_eval_result = await praxos_client.eval_event(notification_data, 'file_change')

            if event_eval_result.get('trigger'):
                logger.info(f"Trigger fired for OneDrive notification")

                for rule_id, action_data in event_eval_result.get('fired_rule_actions_details', {}).items():
                    if isinstance(action_data, str):
                        action_data = json.loads(action_data)

                    rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                    if not rule_details:
                        logger.error(f"No trigger details found in DB for rule_id {rule_id}. Trigger may be inactive, deleted, or flawed.")
                        continue

                    # Build COMMAND string
                    COMMAND = ""
                    COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                    COMMAND += f"Now, upon detecting a file change in OneDrive at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action in action_data:
                        COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                        COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action, default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. If you are unsure about any action, please ask the user for confirmation before proceeding. \n\n The event (OneDrive file change) that triggered this action is as follows: "

                    # Create normalized payload for triggered event
                    normalized_payload = {
                        "text": COMMAND + json.dumps(notification_data, indent=2),
                        "notification_data": notification_data,
                        "resource": resource,
                        "change_type": change_type
                    }

                    ingestion_event = {
                        "user_id": str(user_id),
                        "source": "triggered",
                        "payload": normalized_payload,
                        "logging_context": {
                            "user_id": user_id_var.get(),
                            "request_id": str(request_id_var.get()),
                            "modality": "triggered",
                        },
                        "metadata": {
                            "ingest_type": "onedrive_webhook_triggered",
                            "source": "onedrive",
                            "webhook_event": True,
                            "change_type": change_type,
                            "subscription_id": subscription_id,
                            "conversation_id": rule_details.get('conversation_id'),
                            "resource": resource,
                        },
                    }
                    if not ingestion_event["metadata"].get("conversation_id"):
                        ingestion_event['metadata'].pop('conversation_id', None)

                    await event_queue.publish(ingestion_event)
                    logger.info(f"Published triggered event for OneDrive notification based on rule {rule_id}")
            else:
                logger.info(f"Evaluation found no trigger for OneDrive notification. Proceeding with normal ingestion.")

            # Normal event ingestion (for non-triggered or additional processing)
            event = {
                "user_id": str(user_id),
                "source": "event_ingestion",
                "payload": notification_data,
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
