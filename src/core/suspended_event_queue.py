import json
from typing import Any, Dict
from datetime import datetime

from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger


logger = setup_logger(__name__)

NORMAL_EVENT_KEY = "normal"
SCHEDULE_EVENT_KEY = "schedule"

class SuspendedEventQueue:

    def _generate_session_id(self, event: Dict[str, Any]) -> str:
        """Generate a session ID based on event data if not provided"""
        # Generate session based on user and source for grouping
        user_id = event.get('user_id')
        
        if user_id:
            return f"{user_id}"
        else:
            # Fallback for system/non-user events
            return f"system"

    async def publish(self, event: Dict[str, Any]):
        """
        Publish an event to the Service Bus queue with a session for message grouping.
        Session ID is auto-generated based on user_id and source if not provided.
        This queue is just used of users who send a request when they don't have an active subscription, either thier trial period is ended or there is no billing information about them
        """
        from azure.servicebus.aio import ServiceBusClient
        from azure.servicebus import ServiceBusMessage
        try:
            # Always ensure we have a session ID
            session_id = self._generate_session_id(event)
            
            async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
                sender = client.get_queue_sender(settings.AZURE_SERVICEBUS_SUSPENDED_QUEUE_NAME)
                async with sender:
                    suspended_message = {
                        "event": event,
                        "type": NORMAL_EVENT_KEY
                    }
                    message_body = json.dumps(suspended_message)
                    message = ServiceBusMessage(message_body)
                    message.session_id = session_id
                    await sender.send_messages(message)
                    logger.info(f"An event is suspended with session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to publish suspended event to Azure Service Bus: {e}", exc_info=True)

    async def publish_scheduled_event(self, event: Dict[str, Any], timestamp: datetime):
        """
        Publish an event to the Service Bus queue, at a specific timestamp.
        """
        from azure.servicebus.aio import ServiceBusClient
        from azure.servicebus import ServiceBusMessage
        try:
            async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
                sender = client.get_queue_sender(settings.AZURE_SERVICEBUS_SUSPENDED_QUEUE_NAME)
                async with sender:
                    suspended_message = {
                        "event": event,
                        "type": SCHEDULE_EVENT_KEY,
                        "schedule_time": timestamp.isoformat() if timestamp else None
                    }
                    message_body = json.dumps(suspended_message)
                    message = ServiceBusMessage(message_body)
                    message.scheduled_enqueue_time_utc = timestamp
                    await sender.send_messages(message)
                    logger.info(f"Scheduled event to be enqueued at {timestamp.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to publish scheduled event to Azure Service Bus: {e}", exc_info=True)

suspended_event_queue = SuspendedEventQueue()

async def _process_suspended_events_background(user_id: str):
    """
    Background task to process suspended events for a user
    """
    try:
        from azure.servicebus.aio import ServiceBusClient
        async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
            session_receiver = client.get_queue_receiver(
                settings.AZURE_SERVICEBUS_SUSPENDED_QUEUE_NAME,
                session_id=user_id,
                max_wait_time=30
            )

            async with session_receiver:
                logger.info(f"Processing suspended events for user {user_id}")

                messages_counter = 0

                while True:
                    from src.core.event_queue import event_queue
                    try:
                        batch = await session_receiver.receive_messages(max_message_count=10)

                        if not batch:
                            logger.info(f"Completed processing {messages_counter} suspended events for user {user_id}")
                            return

                        for msg in batch:
                            try:
                                message_body = json.loads(str(msg))
                                messages_counter += 1
                                await session_receiver.complete_message(msg)
                                message_type = message_body.get('type')
                                event = message_body.get('event')
                                if not event:
                                    logger.error(f"there is no event in the suspended message {message_body}" )
                                    continue
                                
                                if message_type == NORMAL_EVENT_KEY:
                                    await event_queue.publish(event)
                                elif message_type == SCHEDULE_EVENT_KEY:
                                    schedule_time = message_body.get('schedule_time')
                                    if not schedule_time:
                                        logger.error(f"can't find schedule time for schedule suspended message {message_body}")
                                        continue
                                    await event_queue.publish_scheduled_event(event, datetime.fromisoformat(schedule_time))
                                else:
                                    logger.error(f'message type {message_type} is not supported')
                                    continue

                            except Exception as e:
                                logger.error(f"Error processing message: {e}", exc_info=True)
                                await session_receiver.abandon_message(msg)

                    except Exception as batch_error:
                        logger.error(f"Error receiving message batch: {batch_error}", exc_info=True)
                        break
    except Exception as e:
        logger.error(f"Background processing error for user {user_id}: {e}", exc_info=True)

from fastapi import APIRouter, status, Query
router = APIRouter()

@router.post("/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def resend_suspended_events(user_id: str = Query(...)):
    """
    Forward all suspended events for a user to event queue
    """
    import asyncio

    # Start background processing without waiting
    asyncio.create_task(_process_suspended_events_background(user_id))

    # Return immediately with 202 status
    return {"message": "Processing started"}
