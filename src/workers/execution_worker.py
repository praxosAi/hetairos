from datetime import datetime
from importlib import metadata
from typing import Optional
from src.core.event_queue import event_queue
from bson import ObjectId
import re

from src.core.agent_runner_langgraph import LangGraphAgentRunner
from src.core.context import create_user_context
from src.tools.tool_types import ErrorDetails, ToolExecutionResponse, ErrorCategory
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.services.scheduling_service import scheduling_service
from src.ingest.ingestion_worker import InitialIngestionCoordinator
from src.egress.service import egress_service
from src.utils.database import conversation_db
import uuid
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
                
            
            # Handle grouped messages (WhatsApp/Telegram rapid messages or forwards)
            if is_grouped and len(events) > 1:
                ### now, we put the metadata for logging.
                
                logger.info(f"Processing session {session_id} with {len(events)} event(s), grouped: {is_grouped}")
                logging_context = events[0].get('logging_context', {})
                if logging_context:
                    #{'user_id': str(user_record["_id"]), 'request_id': str(request_id_var.get()), 'modality': modality_var.get() }
                    user_id_var.set(logging_context.get('user_id','annonymous'))
                    request_id_var.set(logging_context.get('request_id',uuid.uuid4().hex))
                    modality_var.set(logging_context.get('modality','no_modality'))
                else:
                    user_id_var.set(events[0].get('user_id','annonymous'))
                    request_id_var.set(uuid.uuid4().hex)
                    modality_var.set(events[0].get('source','no_modality'))
                await self.handle_grouped_events(events, session_id)
            else:
                # Single event processing (existing logic)
                for event in events:
                    logging_context = event.get('logging_context', {})
                    if logging_context:
                        #{'user_id': str(user_record["_id"]), 'request_id': str(request_id_var.get()), 'modality': modality_var.get() }
                        user_id_var.set(logging_context.get('user_id','annonymous'))
                        request_id_var.set(logging_context.get('request_id',uuid.uuid4().hex))
                        modality_var.set(logging_context.get('modality','no_modality'))
                    else:
                        user_id_var.set(event.get('user_id','annonymous'))
                        request_id_var.set(uuid.uuid4().hex)
                        modality_var.set(event.get('source','no_modality'))
                    await self.handle_single_event(event)

    async def handle_grouped_events(self, events, session_id):
        """Handle multiple related events as a group (e.g., forwarded messages)"""
        try:
            logger.info(f"Processing {len(events)} grouped events from session {session_id}")
            
            # Use the first event as the base context
            base_event = events[0]
            source = base_event.get("source")
            
            if source in ["whatsapp", "telegram",'imessage']:
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
        finally:
            # Reset context variables after processing the group
            user_id_var.set('SYSTEM_LEVEL')
            request_id_var.set('SYSTEM_LEVEL')
            modality_var.set('SYSTEM_LEVEL')
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

    async def handle_async_single_event(self, event) -> tuple[bool, list]:
        """Handle a single event that may involve asynchronous tasks (e.g., browser tool)"""
        if event.get("source") not in ["browser_tool"]:
            return True, []
        
        conversation_id = event.get("metadata", {}).get("conversation_id")

        if not conversation_id:
            logger.error(f"Async event missing conversation_id in metadata: {event}")
            return False, []
        
        user_id = event.get("user_id")
        if not user_id:
            logger.error(f"Async event missing user_id: {event}")
            return False, []
        
        tool_call_id = event.get("metadata", {}).get("tool_call_id")
        if not tool_call_id:
            logger.error(f"Async event missing tool_call_id in metadata: {event}")
            return False, []
        
        prev_message = await conversation_db.messages.find_one({
            "conversation_id": ObjectId(conversation_id),
            "user_id": ObjectId(user_id),
            "metadata.tool_call_id": tool_call_id
        })

        if not prev_message:
            logger.error(f"Could not find previous message for async event: {event}")
            return False, []
        
        if not prev_message.get("metadata", {}).get("asynchronous_task_status") == "success":
            tool_result_json = prev_message.get("content", "")
            tool_result = ToolExecutionResponse.model_validate_json(tool_result_json)

            event_payload = event.get('payload', {})
            tool_result.result = event_payload.get('text','')
            if event_payload.get('error'):
                tool_result.error_details = ErrorDetails(
                    error_message=event_payload.get('error'),
                    operation="browser_tool_execution",
                    category=ErrorCategory.IINTERNAL_ERROR
                )

            await conversation_db.messages.update_one(
                {"_id": prev_message["_id"]},
                {"$set": {
                    "content": f"{tool_result}", 
                    "metadata.asynchronous_task_status": "success",
                    "metadata.asynchronous_task_recieved_at": datetime.utcnow()
                }}
            )

        requested_tasks = await conversation_db.messages.find({
            "conversation_id": ObjectId(conversation_id),
            "user_id": ObjectId(user_id),
            "metadata.asynchronous_task_status": "requested"
        }).to_list()

        if not requested_tasks:
            return True, []
        else:
            pending_tasks = [task.get("metadata", {}).get("tool_name") for task in requested_tasks]
            return False, pending_tasks
        
            


    async def handle_single_event(self, event):
        """Handle a single event (original logic)"""
        try:
            logger.info(f"Processing single event: {event}")
            source = event.get("source")
            
            if source == "ingestion":
                await self.ingestion_coordinator.perform_initial_ingestion(
                    user_id=event["user_id"],
                    integration_id=event["payload"]["integration_id"]
                )
                # Ingestion tasks typically don't have a direct response to the user.
                # We could potentially send a notification via the egress service if needed.
            elif source == "file_ingestion":
                await self.ingestion_coordinator.ingest_uploaded_files(
                    user_id=event["user_id"],
                    files=event["payload"]["files"],
                )
            elif source == 'event_ingestion':
                pass
                # await self.ingestion_coordinator.ingest_event(
                #     user_id=event["user_id"],
                #     event_details=event["payload"]
                # )

            elif source in ["recurring", "scheduled", "websocket", "email", "whatsapp","telegram",'imessage','triggered','slack','discord','mcp','browser_tool']:
                # --- Handle Agent Task ---

                if source in ['scheduled', 'recurring']:
                    task_active = await scheduling_service.verify_task_active(event["metadata"]["task_id"])
                    if not task_active:
                        logger.info(f"Task is cancelled for event: {event}")
                        return  # Changed from continue to return
                if source == "recurring":
                    try:
                        logger.info(f"Scheduling next run for recurring event: {event}")
                        await scheduling_service.schedule_next_run(event)
                    except Exception as e:
                        logger.error(f"Error scheduling next run for recurring event: {event}, {e}", exc_info=True)
                # For browser_tool results, use the original_source for routing
                if source == "browser_tool":
                    original_source = event.get("metadata", {}).get("original_source")
                    if original_source:
                        # Override output_type to ensure proper routing back to original platform
                        event["output_type"] = original_source
                        logger.info(f"Browser result will be routed to original source: {original_source}")
                
                    
                is_done, pending_tasks = await self.handle_async_single_event(event)
                if not is_done:
                    logger.info(f"Async tasks pending for browser_tool event: {event}, tasks: {pending_tasks}")
                    return  # Changed from continue to return

                user_context = await create_user_context(event["user_id"])
                if not user_context:
                    logger.error(f"Could not create user context for user {event['user_id']}. Skipping event.")
                    return  # Changed from continue to return
                has_media = await self.determine_media_presence(event)

                # Start activity indicator (typing for Telegram)
                typing_task_id = await egress_service.start_typing_indicator(event)

                self.langgraph_agent_runner = LangGraphAgentRunner(trace_id=f"exec-{str(event['user_id'])}-{datetime.utcnow().isoformat()}", has_media=has_media)
                result = await self.langgraph_agent_runner.run(
                    user_context=user_context,
                    input=event["payload"],
                    source=source,
                    metadata=event.get("metadata", {})
                )
                await self.post_process_langgraph_response(result, event, typing_task_id)
            
            else:
                logger.warning(f"Unknown event source: {source}. Skipping event.")

        except Exception as e:
            logger.error(f"Error processing single event {event}: {e}", exc_info=True)
        finally:
            # Reset context variables after processing the event
            user_id_var.set('SYSTEM_LEVEL')
            request_id_var.set('SYSTEM_LEVEL')
            modality_var.set('SYSTEM_LEVEL')
    async def post_process_langgraph_response(self, result: dict, event: dict, typing_task_id: Optional[str] = None):
        """Post-process agent response, handling cases where agent used messaging tools directly."""

        # Stop typing indicator
        await egress_service.stop_typing_indicator(typing_task_id)

        # Check if response is empty (agent used messaging tools)
        if not result.response or result.response.strip() == "":
            logger.info("No fallback response needed - agent used communication tools directly")
            return

        # Fallback was used - send via egress service
        logger.info("Sending fallback response via egress service")
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
