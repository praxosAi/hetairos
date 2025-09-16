import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

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

    async def publish(self, event: Dict[str, Any], session_id: str = None):
        await self._queue.put(event)
        logger.info(f"Published immediate event to in-memory queue: {event.get('type')}")
        if session_id:
            logger.info(f"Session ID {session_id} ignored in in-memory mode")

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

    def _generate_session_id(self, event: Dict[str, Any], session_id: str = None) -> str:
        """Generate a session ID based on event data if not provided"""
        if session_id:
            return session_id
            
        # Generate session based on user and source for grouping
        user_id = event.get('user_id')
        source = event.get('source', 'unknown')
        
        if user_id:
            return f"{source}_{user_id}"
        else:
            # Fallback for system/non-user events
            return f"system_{source}"
    
    def _calculate_adaptive_delay(self, messages: List[Dict[str, Any]]) -> float:
        """Calculate adaptive delay based on message characteristics, max 500ms"""
        base_delay = 0.1  # 100ms base delay
        
        if not messages:
            return base_delay
        
        # Get the latest message for analysis
        latest_message = messages[-1]
        
        # Check for forwarded messages
        is_forwarded = latest_message.get('metadata', {}).get('forwarded', False)
        
        # Check for files in any message
        has_files = any(
            'files' in msg.get('payload', {}) and msg.get('payload', {}).get('files')
            for msg in messages
        )
        
        # Check message count (more messages = likely part of a sequence)
        message_count = len(messages)
        
        # Calculate adaptive delay
        delay = base_delay
        
        # Add delay for forwarded messages (they often come in groups)
        if is_forwarded:
            delay += 0.2  # +200ms for forwards
            
        # Add delay for files (uploads can have network delays)
        if has_files:
            delay += 0.1  # +100ms for files
            
        # Add small delay for message sequences (diminishing returns)
        if message_count > 1:
            sequence_delay = min(0.1, 0.02 * message_count)  # +20ms per message, max 100ms
            delay += sequence_delay
        
        # Cap at 500ms maximum
        delay = min(0.5, delay)
        
        logger.debug(f"Delay calculation: base={base_delay}, forwarded={is_forwarded}, "
                    f"files={has_files}, count={message_count}, final={delay}")
        
        return delay

    async def publish(self, event: Dict[str, Any], session_id: str = None):
        """
        Publish an event to the Service Bus queue with a session for message grouping.
        Session ID is auto-generated based on user_id and source if not provided.
        """
        from azure.servicebus.aio import ServiceBusClient
        from azure.servicebus import ServiceBusMessage
        try:
            # Always ensure we have a session ID
            final_session_id = self._generate_session_id(event, session_id)
            
            async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
                sender = client.get_queue_sender(settings.AZURE_SERVICEBUS_QUEUE_NAME)
                async with sender:
                    message_body = json.dumps(event)
                    message = ServiceBusMessage(message_body)
                    message.session_id = final_session_id
                    
                    await sender.send_messages(message)
                    logger.info(f"Published event to session: {final_session_id}")
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

    # async def consume(self):
    #     """
    #     A generator that yields consumed messages from the queue.
    #     It will run indefinitely, waiting for new messages.
    #     """
    #     from azure.servicebus.aio import ServiceBusClient
    #     while True:
    #         try:
    #             async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
    #                 receiver = client.get_queue_receiver(settings.AZURE_SERVICEBUS_QUEUE_NAME)
    #                 async with receiver:
    #                     logger.info("Event consumer started. Waiting for messages...")
    #                     async for msg in receiver:
    #                         try:
    #                             event = json.loads(str(msg))
    #                             yield event
    #                             await receiver.complete_message(msg)
    #                         except Exception as e:
    #                             logger.error(f"Error processing message: {e}", exc_info=True)
    #                             await receiver.abandon_message(msg)
    #         except Exception as e:
    #             logger.error(f"Service Bus connection error in consumer: {e}. Reconnecting in 10 seconds...", exc_info=True)
    #             await asyncio.sleep(10)

    async def consume(self):
        """
        A generator that yields messages grouped by session (user).
        Falls back to individual message processing if sessions aren't enabled.
        """
        from azure.servicebus.aio import ServiceBusClient
        from azure.servicebus import NEXT_AVAILABLE_SESSION
        while True:
            try:
                async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
                    # Try session-based approach first
                    try:
                        session_receiver = client.get_queue_receiver(
                            settings.AZURE_SERVICEBUS_QUEUE_NAME,
                            session_id=NEXT_AVAILABLE_SESSION
                        )
                        
                        async with session_receiver:
                            session_id = session_receiver.session.session_id
                            logger.info(f"Processing session: {session_id}")
                            
                            # Collect messages from this session with brief wait for grouping
                            messages = []
                            
                            # Collect messages in this session with grouping logic
                            first_message_received = False

                            while True:
                                try:
                                    # First message: wait longer (30s), subsequent: shorter wait (2s for grouping)
                                    wait_time = 30 if not first_message_received else 2

                                    batch = await session_receiver.receive_messages(max_message_count=10, max_wait_time=wait_time)

                                    if not batch:
                                        if first_message_received:
                                            # We got some messages but now timeout - process what we have
                                            break
                                        else:
                                            # No messages at all in this session, continue to next session
                                            break

                                    # Process the batch
                                    for msg in batch:
                                        try:
                                            event = json.loads(str(msg))
                                            messages.append(event)
                                            await session_receiver.complete_message(msg)
                                            first_message_received = True

                                        except Exception as e:
                                            logger.error(f"Error processing message: {e}", exc_info=True)
                                            await session_receiver.abandon_message(msg)


                                except Exception as batch_error:
                                    logger.error(f"Error receiving message batch: {batch_error}", exc_info=True)
                                    break
                            
                            if messages:
                                yield {
                                    'session_id': session_id,
                                    'events': messages,
                                    'is_grouped': len(messages) > 1
                                }
                    
                    except Exception as session_error:
                        if "does not require sessions" in str(session_error) or "RequiresSession" in str(session_error):
                            logger.warning("Service Bus queue doesn't have sessions enabled, falling back to individual message processing")
                            # Fall back to non-session processing
                            receiver = client.get_queue_receiver(settings.AZURE_SERVICEBUS_QUEUE_NAME)
                            async with receiver:
                                logger.info("Using individual message processing (no sessions)")
                                async for msg in receiver:
                                    try:
                                        event = json.loads(str(msg))
                                        # Yield as single-message group for compatibility
                                        yield {
                                            'session_id': 'no-session',
                                            'events': [event],
                                            'is_grouped': False
                                        }
                                        await receiver.complete_message(msg)
                                    except Exception as e:
                                        logger.error(f"Error processing individual message: {e}", exc_info=True)
                                        await receiver.abandon_message(msg)
                            return  # Exit the session retry loop
                        elif "no messages available" not in str(session_error).lower():
                            logger.error(f"Session processing error: {session_error}", exc_info=True)
                        await asyncio.sleep(1)  # Brief pause before trying again
            
            except Exception as e:
                logger.error(f"Service Bus connection error in session consumer: {e}. Reconnecting in 10 seconds...", exc_info=True)
                await asyncio.sleep(10)

def get_event_queue():
    if settings.QUEUE_MODE == 'in_memory':
        return InMemoryEventQueue()
    else:
        return AzureEventQueue()

# Global instance
event_queue = get_event_queue()