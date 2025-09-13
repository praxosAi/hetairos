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
        async for event in event_queue.consume():
            if not event:
                continue
            
            try:
                logger.info(f"Consumed event: {event}")
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
                            continue

                    user_context = await create_user_context(event["user_id"])
                    if not user_context:
                        logger.error(f"Could not create user context for user {event['user_id']}. Skipping event.")
                        continue
                    has_media = False
                    for file in event.get('payload', {}).get('files', []):
                        if file.get('type') in ['voice','video','audio','image','file','document']:
                            has_media = True
                            logger.info(f"Event has media file, setting has_audio to True so we use gemini-2.5-pro model")
                            break
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
                logger.error(f"Error processing event {event}: {e}", exc_info=True)

    async def post_process_langgraph_response(self, result: dict, event: dict):
        event["output_type"] = result.delivery_modality
        await egress_service.send_response(event, {"response": result.response})

async def execution_task():
    """Entry point for the execution worker background task."""
    worker = ExecutionWorker()
    await worker.run()
