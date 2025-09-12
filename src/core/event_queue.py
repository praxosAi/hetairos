import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)

class InMemoryEventQueue:
    """An in-memory event queue for local development."""
    def __init__(self):
        self._queue = asyncio.Queue()
        self._scheduled_tasks = {}
        logger.info("Initialized in-memory event queue.")

    async def _schedule_event(self, event: Dict[str, Any], timestamp: datetime):
        delay = (timestamp - datetime.now(timezone.utc)).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await self._queue.put(event)
        logger.info(f"In-memory event enqueued: {event.get('type')}")

    async def publish(self, event: Dict[str, Any]):
        await self._queue.put(event)
        logger.info(f"Published immediate event to in-memory queue: {event.get('type')}")

    async def publish_scheduled_event(self, event: Dict[str, Any], timestamp: datetime):
        task = asyncio.create_task(self._schedule_event(event, timestamp))
        self._scheduled_tasks[event.get("id", str(timestamp))] = task
        logger.info(f"Scheduled event in-memory for {timestamp.isoformat()}")

    async def consume(self):
        logger.info("In-memory event consumer started. Waiting for messages...")
        while True:
            try:
                event = await self._queue.get()
                yield event
                self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("In-memory consumer task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error processing in-memory event: {e}", exc_info=True)


class AzureEventQueue:
    """An Azure Service Bus-based event queue that supports immediate and scheduled messages."""

    async def publish(self, event: Dict[str, Any]):
        """
        Publish an event to the Service Bus queue, either immediately or after a delay.
        """
        from azure.servicebus.aio import ServiceBusClient
        from azure.servicebus import ServiceBusMessage
        try:
            async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
                sender = client.get_queue_sender(settings.AZURE_SERVICEBUS_QUEUE_NAME)
                async with sender:
                    message_body = json.dumps(event)
                    message = ServiceBusMessage(message_body)
                    await sender.send_messages(message)
                    logger.info("Published immediate event to Service Bus.")
        except Exception as e:
            logger.error(f"Failed to publish event to Azure Service Bus: {e}", exc_info=True)

    async def publish_scheduled_event(self, event: Dict[str, Any], timestamp: datetime):
        """
        Publish an event to the Service Bus queue, at a specific timestamp.
        """
        from azure.servicebus.aio import ServiceBusClient
        from azure.servicebus import ServiceBusMessage
        try:
            async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
                sender = client.get_queue_sender(settings.AZURE_SERVICEBUS_QUEUE_NAME)
                async with sender:
                    message_body = json.dumps(event)
                    message = ServiceBusMessage(message_body)
                    message.scheduled_enqueue_time_utc = timestamp
                    await sender.send_messages(message)
                    logger.info(f"Scheduled event to be enqueued at {timestamp.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to publish scheduled event to Azure Service Bus: {e}", exc_info=True)

    async def consume(self):
        """
        A generator that yields consumed messages from the queue.
        It will run indefinitely, waiting for new messages.
        """
        from azure.servicebus.aio import ServiceBusClient
        while True:
            try:
                async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
                    receiver = client.get_queue_receiver(settings.AZURE_SERVICEBUS_QUEUE_NAME)
                    async with receiver:
                        logger.info("Event consumer started. Waiting for messages...")
                        async for msg in receiver:
                            try:
                                event = json.loads(str(msg))
                                yield event
                                await receiver.complete_message(msg)
                            except Exception as e:
                                logger.error(f"Error processing message: {e}", exc_info=True)
                                await receiver.abandon_message(msg)
            except Exception as e:
                logger.error(f"Service Bus connection error in consumer: {e}. Reconnecting in 10 seconds...", exc_info=True)
                await asyncio.sleep(10)

def get_event_queue():
    if settings.QUEUE_MODE == 'in_memory':
        return InMemoryEventQueue()
    else:
        return AzureEventQueue()

# Global instance
event_queue = get_event_queue()