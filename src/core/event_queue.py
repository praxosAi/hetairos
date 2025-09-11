import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage

from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)
class EventQueue:
    """An Azure Service Bus-based event queue that supports immediate and scheduled messages."""

    async def publish(self, event: Dict[str, Any]):
        """
        Publish an event to the Service Bus queue, either immediately or after a delay.
        """
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


# Global instance
event_queue = EventQueue()
