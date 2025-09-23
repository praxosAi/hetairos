import asyncio
from datetime import datetime
import logging
from src.core.event_queue import event_queue

from src.core.agent_runner_langgraph import LangGraphAgentRunner
from src.core.context import create_user_context
from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger
from src.services.scheduling_service import scheduling_service
from src.ingest.ingestion_worker import InitialIngestionCoordinator
from src.egress.service import egress_service

logger = setup_logger(__name__)

class ExecutionWorker:
    """
    Listens to the event queue and triggers the appropriate action based on the event source.
    """
    def __init__(self):
        
        self.ingestion_coordinator = InitialIngestionCoordinator()

    async def run(self):
        """Main loop to consume events from the queue and execute them."""
        logger.info("Starting execution worker...")
        async for session_data in event_queue.consume():
            if not session_data:
                continue
            
            session_id = session_data.get('session_id')
            events = session_data.get('events', [])
            is_grouped = session_data.get('is_grouped', False)
            
            if not events:
                continue
                
            logger.info(f"Processing session {session_id} with {len(events)} event(s), grouped: {is_grouped}")
            
            # Handle grouped messages (WhatsApp/Telegram rapid messages or forwards)
            if is_grouped and len(events) > 1:
                await self.handle_grouped_events(events, session_id)
            else:
                # Single event processing (existing logic)
                for event in events:
                    await self.handle_single_event(event)

    async def handle_grouped_events(self, events, session_id):
        """Handle multiple related events as a group (e.g., forwarded messages)"""
        try:
            logger.info(f"Processing {len(events)} grouped events from session {session_id}")
            
            # Use the first event as the base context
            base_event = events[0]
            source = base_event.get("source")
            
            if source in ["whatsapp", "telegram"]:
                # Combine messages for chat platforms
                combined_payload = self.combine_chat_messages(events)
                combined_event = {**base_event}
                combined_event["payload"] = combined_payload
                combined_event["metadata"] = {
                    **base_event.get("metadata", {}),
                    "grouped": True,
                    "message_count": len(events),
                    "session_id": session_id
                }
                
                await self.handle_single_event(combined_event)
            else:
                # For non-chat events, process individually
                for event in events:
                    await self.handle_single_event(event)
                    
        except Exception as e:
            logger.error(f"Error processing grouped events from session {session_id}: {e}", exc_info=True)

    def combine_chat_messages(self, events):
        """Combine multiple chat messages into a structured payload list"""
        combined_payload = []
        
        for event in events:
            payload = event.get("payload", {})
            metadata = event.get("metadata", {})
            
            # Create structured message entry
            message_entry = {
                "metadata": {
                    "timestamp": metadata.get("timestamp"),
                    "message_id": metadata.get("message_id"),
                    "forwarded": metadata.get("forwarded", False)
                }
            }
            message_entry.update(payload)
            # Add forwarding context if present
            if metadata.get("forwarded") and metadata.get("forward_origin"):
                message_entry["metadata"]["forward_origin"] = metadata.get("forward_origin")
            
            combined_payload.append(message_entry)
        
        return combined_payload



    async def handle_single_event(self, event):
        """Handle a single event (original logic)"""
        try:
            logger.info(f"Processing single event: {event}")
            source = event.get("source")
            
            if source == "ingestion":
                await self.ingestion_coordinator.perform_initial_ingestion(
                    user_id=event["user_id"],
                    integration_type=event["payload"]["integration_type"]
                )
                # Ingestion tasks typically don't have a direct response to the user.
                # We could potentially send a notification via the egress service if needed.
            elif source == "file_ingestion":
                await self.ingestion_coordinator.ingest_uploaded_files(
                    user_id=event["user_id"],
                    files=event["payload"]["files"],
                )

            elif source in ["recurring", "scheduled", "websocket", "email", "whatsapp","telegram"]:
                # --- Handle Agent Task ---
                if source == "recurring":
                    try:
                        logger.info(f"Scheduling next run for recurring event: {event}")
                        await scheduling_service.schedule_next_run(event["metadata"]["task_id"])
                    except Exception as e:
                        logger.error(f"Error scheduling next run for recurring event: {event}", exc_info=True)
                
                if source in ['scheduled', 'recurring']:
                    task_active = await scheduling_service.verify_task_active(event["metadata"]["task_id"])
                    if not task_active:
                        logger.info(f"Task is cancelled for event: {event}")
                        return  # Changed from continue to return

                user_context = await create_user_context(event["user_id"])
                if not user_context:
                    logger.error(f"Could not create user context for user {event['user_id']}. Skipping event.")
                    return  # Changed from continue to return
                has_media = await self.determine_media_presence(event)
                

                self.langgraph_agent_runner = LangGraphAgentRunner(trace_id=f"exec-{str(event['user_id'])}-{datetime.utcnow().isoformat()}", has_media=has_media)
                result = await self.langgraph_agent_runner.run(
                    user_context=user_context,
                    input=event["payload"],
                    source=source,
                    metadata=event.get("metadata", {})
                )
                await self.post_process_langgraph_response(result, event)
            
            else:
                logger.warning(f"Unknown event source: {source}. Skipping event.")

        except Exception as e:
            logger.error(f"Error processing single event {event}: {e}", exc_info=True)

    async def post_process_langgraph_response(self, result: dict, event: dict):
        event["output_type"] = result.delivery_platform
        await egress_service.send_response(event, {"response": result.response, "file_links": result.file_links})


    async def determine_media_presence(self, event: dict) -> bool:
        has_media = False
        if isinstance(event.get('payload'), list):
            for item in event['payload']:
                if item.get('type') in ['voice','video','audio','image','file','document']:
                    has_media = True
                    logger.info(f"Event has media file, setting has_audio to True so we use gemini-2.5-pro model")
                    break
        elif isinstance(event.get('payload'), dict):
            for file in event.get('payload', {}).get('files', []):
                if file.get('type') in ['voice','video','audio','image','file','document']:
                    has_media = True
                    logger.info(f"Event has media file, setting has_audio to True so we use gemini-2.5-pro model")
                    break
        else:
            logger.info(f"Event payload is neither list nor dict, cannot determine media presence: {event.get('payload')}")
        return has_media

async def execution_task():
    """Entry point for the execution worker background task."""
    worker = ExecutionWorker()
    await worker.run()
