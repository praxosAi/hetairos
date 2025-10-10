from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.config.settings import settings
from src.core.praxos_client import PraxosClient
from src.utils.database import db_manager
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
from datetime import datetime, timezone
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

            # Extract event ID from resource path (e.g., "Users/{user_id}/Events/{event_id}")
            event_id = resource.split("/")[-1] if "/" in resource else None

            # Fetch full event details from Microsoft Graph API
            event_data = None
            if event_id and change_type != "deleted":
                try:
                    graph_integration = MicrosoftGraphIntegration(user_id)
                    if await graph_integration.authenticate():
                        event_data = await graph_integration.get_event_by_id(event_id)
                        logger.info(f"Fetched event details for {event_id}: {event_data.get('title') if event_data else 'None'}")
                    else:
                        logger.error(f"Failed to authenticate Microsoft Graph for user {user_id}")
                except Exception as e:
                    logger.error(f"Error fetching event details for {event_id}: {e}", exc_info=True)

            # Prepare notification data for trigger evaluation
            notification_data = {
                "subscription_id": subscription_id,
                "change_type": change_type,
                "resource": resource,
                "event_id": event_id
            }

            # Add full event details if available
            if event_data:
                notification_data.update(event_data)

            # Evaluate triggers using PraxosClient
            praxos_api_key = user_record.get("praxos_api_key")
            praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

            logger.info(f"Evaluating triggers for calendar event {event_id}")
            event_eval_result = await praxos_client.eval_event(notification_data, 'calendar_event')

            if event_eval_result.get('trigger'):
                logger.info(f"Trigger fired for calendar event {event_id}")

                for rule_id, action_data in event_eval_result.get('fired_rule_actions_details', {}).items():
                    if isinstance(action_data, str):
                        action_data = json.loads(action_data)

                    rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                    if not rule_details:
                        logger.error(f"No trigger details found in DB for rule_id {rule_id}. Trigger may be inactive, deleted, or flawed.")
                        continue

                    # Build COMMAND string with trigger context
                    COMMAND = ""
                    COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                    COMMAND += f"Now, upon receiving a calendar event notification, at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action in action_data:
                        COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                        COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action, default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. If you are unsure about any action, please ask the user for confirmation before proceeding. \n\n The event (calendar event, in this case) that triggered this action is as follows: "

                    # Build normalized payload with calendar event details
                    normalized_payload = {
                        "text": COMMAND + json.dumps(notification_data, indent=2, default=str)
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
                            "ingest_type": "microsoft_calendar_webhook_triggered",
                            "source": "microsoft_calendar",
                            "webhook_event": True,
                            "change_type": change_type,
                            "event_id": event_id,
                            "subscription_id": subscription_id,
                            "conversation_id": rule_details.get('conversation_id'),
                        },
                    }

                    # Add event details to metadata if available
                    if event_data:
                        ingestion_event["metadata"].update({
                            "title": event_data.get("title"),
                            "start": event_data.get("start"),
                            "end": event_data.get("end"),
                            "location": event_data.get("location"),
                        })

                    if not ingestion_event["metadata"].get("conversation_id"):
                        ingestion_event['metadata'].pop('conversation_id', None)

                    await event_queue.publish(ingestion_event)
                    logger.info(f"Published triggered event for calendar event {event_id} based on rule {rule_id}")
            else:
                logger.info(f"Evaluation found no trigger for calendar event {event_id}. Proceeding with normal ingestion.")

            # Normal event publishing (commented out, matching Gmail pattern)
            # event = {
            #     "user_id": str(user_id),
            #     "source": "event_ingestion",
            #     "payload": {
            #         "subscription_id": subscription_id,
            #         "change_type": change_type,
            #         "resource": resource
            #     },
            #     "logging_context": {
            #         'user_id': user_id_var.get(),
            #         'request_id': str(request_id_var.get()),
            #         'modality': 'microsoft_calendar_webhook'
            #     },
            #     "metadata": {
            #         'ingest_type': 'microsoft_calendar_webhook',
            #         'source': 'microsoft_calendar',
            #         'webhook_event': True,
            #         'change_type': change_type,
            #         'subscription_id': subscription_id
            #     }
            # }
            # await event_queue.publish(event)

            logger.info(f"Processed Microsoft Calendar webhook for user {user_id}, change_type: {change_type}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Microsoft Calendar webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
