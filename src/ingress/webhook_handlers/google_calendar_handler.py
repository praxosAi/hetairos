from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
from src.utils.database import db_manager
from src.core.praxos_client import PraxosClient
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from datetime import datetime, timezone
import json

router = APIRouter()
logger = setup_logger(__name__)

@router.post("/google-calendar")
async def handle_google_calendar_webhook(request: Request):
    """
    Handles incoming Google Calendar push notifications.

    This webhook implements the full processing pattern following Gmail:
    1. Receive notification
    2. Find user by resource_id
    3. Get checkpoint (sync token)
    4. If no checkpoint - seed and exit
    5. Fetch changed events since checkpoint
    6. Deduplicate using insert_or_reject_items
    7. Update checkpoint
    8. Evaluate triggers and publish to event queue

    Reference: https://developers.google.com/calendar/api/guides/push
    Reference: https://developers.google.com/calendar/api/guides/sync
    """
    try:
        # Google Calendar sends notifications via headers, not body
        resource_id = request.headers.get("x-goog-resource-id")
        resource_state = request.headers.get("x-goog-resource-state")  # "sync", "exists", or "not_exists"
        channel_id = request.headers.get("x-goog-channel-id")
        channel_token = request.headers.get("x-goog-channel-token")  # Optional verification token

        logger.info(f"Received Google Calendar webhook - Resource ID: {resource_id}, State: {resource_state}, Channel: {channel_id}")

        # Sync notification is sent when watch is first created - acknowledge it
        if resource_state == "sync":
            logger.info("Received Google Calendar sync notification (initial handshake)")
            return {"status": "ok"}

        # No resource ID means invalid notification
        if not resource_id or not channel_id:
            logger.warning("Missing required headers in Google Calendar webhook")
            raise HTTPException(status_code=400, detail="Missing required headers")

        # Find user and connected account by integration resource_id
        # The resource_id is stored in integration.webhook_info.webhook_resource_id
        user_and_account = await integration_service.get_user_and_account_by_webhook_resource_id(resource_id, "google_calendar")

        if not user_and_account:
            logger.warning(f"No user found for Google Calendar resource ID: {resource_id}")
            return {"status": "ok"}  # Return OK to acknowledge webhook

        user_id, connected_account = user_and_account

        if not connected_account:
            logger.error(f"No connected account found for resource ID {resource_id}")
            return {"status": "ok"}

        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            logger.error(f"User not found for ID {user_id}")
            return {"status": "ok"}

        # Authenticate Google Calendar
        try:
            calendar_integration = GoogleCalendarIntegration(user_id)
            if not await calendar_integration.authenticate():
                logger.error(f"Failed to authenticate Google Calendar for user {user_id} and account {connected_account}")
                return {"status": "error", "message": "Failed to authenticate Google Calendar"}
        except Exception as e:
            logger.error(f"Exception during Google Calendar authentication for user {user_id} and account {connected_account}: {e}")
            return {"status": "error", "message": "Exception during Google Calendar authentication"}

        # Get checkpoint (sync token)
        checkpoint = await integration_service.get_calendar_sync_token(user_id, connected_account)
        if not checkpoint:
            # Seed once: perform initial sync to get sync token and exit (no backfill)
            _, new_sync_token = await calendar_integration.get_changed_events_since(None, account=connected_account)
            if new_sync_token:
                await integration_service.set_calendar_sync_token(user_id, connected_account, new_sync_token)
                logger.info(f"Seeded calendar sync token for {connected_account}")
            return {"status": "seeded"}

        # Fetch changed events since checkpoint
        events, new_sync_token = await calendar_integration.get_changed_events_since(
            checkpoint,
            account=connected_account
        )

        # Update checkpoint if we got a new token
        if new_sync_token:
            await integration_service.set_calendar_sync_token(user_id, connected_account, new_sync_token)

        if not events:
            logger.info(f"No new events for {connected_account} since checkpoint (advanced_to={new_sync_token[:20] if new_sync_token else None}...)")
            return {"status": "ok", "fetched": 0, "advanced_to": new_sync_token}

        # Deduplicate events using insert_or_reject_items
        inserted_ids = await db_manager.insert_or_reject_items(
            items=events,
            user_id=user_id,
            platform="google_calendar",
            id_field="id",
            platform_id_field="platform_event_id"
        )
        inserted = [iid for iid in inserted_ids if iid]
        logger.info(f"Fetched {len(events)} events; inserted {len(inserted)} for {connected_account}")

        # Process only those actually inserted
        praxos_api_key = user_record.get("praxos_api_key")
        praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

        for event, inserted_id in zip(events, inserted_ids):
            if not inserted_id:
                logger.info(f"Event {event.get('id')} already processed, skipping.")
                continue

            logger.info(f"Processing new calendar event {event.get('id')}")
            event_eval_result = await praxos_client.eval_event(event, 'calendar_event')

            if event_eval_result.get('trigger'):
                # Process triggered actions (following Gmail pattern)
                for rule_id, action_data in event_eval_result.get('fired_rule_actions_details', {}).items():
                    if isinstance(action_data, str):
                        action_data = json.loads(action_data)

                    rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                    if not rule_details:
                        logger.error(f"No trigger details found in DB for rule_id {rule_id}. trigger may be inactive, deleted, or flawed.")
                        continue

                    COMMAND = ""
                    COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                    COMMAND += f"Now, upon receiving a new calendar event, at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action in action_data:
                        COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                        COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action, default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. If you are unsure about any action, please ask the user for confirmation before proceeding. \n\n The event (calendar event, in this case) that triggered this action is as follows: "

                    # Format calendar event for ingestion
                    event_summary = event.get('summary', 'No Title')
                    event_start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))
                    event_end = event.get('end', {}).get('dateTime', event.get('end', {}).get('date'))
                    event_description = event.get('description', '')

                    normalized = {
                        "payload": {
                            "text": f"{COMMAND}\n\nEvent: {event_summary}\nStart: {event_start}\nEnd: {event_end}\nDescription: {event_description}",
                            "raw_event": event
                        },
                        "metadata": {
                            "event_id": event.get('id'),
                            "event_title": event_summary,
                            "event_start": event_start,
                            "event_end": event_end,
                            "source": "google_calendar"
                        }
                    }

                    ingestion_event = {
                        "user_id": str(user_id),
                        "source": "triggered",
                        "payload": normalized["payload"],
                        "logging_context": {
                            "user_id": user_id_var.get(),
                            "request_id": str(request_id_var.get()),
                            "modality": "triggered",
                        },
                        "metadata": {
                            **normalized["metadata"],
                            "conversation_id": rule_details.get('conversation_id'),
                        },
                    }
                    if not ingestion_event["metadata"].get("conversation_id"):
                        ingestion_event['metadata'].pop('conversation_id', None)

                    await event_queue.publish(ingestion_event)
                    logger.info(f"Published triggered event for calendar event {event.get('id')} based on rule {rule_id}")
            else:
                logger.info(f"Evaluation found no trigger for calendar event {event.get('id')}. Proceeding with normal ingestion.")

            user_id_var.set(str(user_id))
            modality_var.set("google_calendar_webhook")
            if event.get('metadata') is None:
                event['metadata'] = {}
            event['metadata']['inserted_id'] = inserted_id

            ingestion_event = {
                "user_id": str(user_id),
                "source": "event_ingestion",
                "payload": event,
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'ingestion_api'
                },
                "metadata": {
                    'ingest_type': 'google_calendar_webhook',
                    'source': 'google_calendar',
                    'calendar_webhook_event': True,
                    'calendar_event_id': event.get("id"),
                    'inserted_id': inserted_id
                }
            }
            # await event_queue.publish(ingestion_event)

        return {
            "status": "ok",
            "fetched": len(events),
            "inserted": len(inserted),
            "advanced_to": new_sync_token
        }

    except Exception as e:
        logger.error(f"Error processing Google Calendar webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
