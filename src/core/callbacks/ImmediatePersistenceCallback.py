from langchain.callbacks.base import BaseCallbackHandler, AsyncCallbackHandler
from typing import Any, Dict, List, Optional
from uuid import UUID
from src.utils.logging import setup_logger
from src.services.conversation_manager import ConversationManager
from src.core.models import MessageCategory

logger = setup_logger(__name__)

class ImmediatePersistenceCallback(AsyncCallbackHandler):
    """
    Callback handler to immediately persist tool execution results to the database.
    This ensures that tool outputs are saved even if the graph execution fails later,
    and preserves the chronological order of execution.
    """

    def __init__(self, conversation_manager: ConversationManager, conversation_id: str, user_id: str):
        self.conversation_manager = conversation_manager
        self.conversation_id = conversation_id
        self.user_id = user_id

    async def on_chat_model_end(
        self,
        response: Any, # LLMResult
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Run when LLM ends running."""
        try:
            # Extract the generated message
            if not response.generations or not response.generations[0]:
                return
                
            generated_message = response.generations[0][0].message
            
            # Check if it has tool calls
            if hasattr(generated_message, 'tool_calls') and generated_message.tool_calls:
                logger.info(f"Persisting AI Message with {len(generated_message.tool_calls)} tool calls")
                content = generated_message.content if generated_message.content else ""
                await self.conversation_manager.add_assistant_message(
                    user_id=self.user_id,
                    conversation_id=self.conversation_id,
                    content=str(content),
                    metadata={"tool_calls": [tc for tc in generated_message.tool_calls]},
                    message_category=MessageCategory.TOOL_EXECUTION.value
                )
                logger.info("Successfully persisted AI Message with tool calls")
            
            # Check if it has text content (and NO tool calls, or mixed)
            # If mixed, we already saved it above. If text only:
            elif generated_message.content:
                logger.info("Persisting AI Text Message")
                await self.conversation_manager.add_assistant_message(
                    user_id=self.user_id,
                    conversation_id=self.conversation_id,
                    content=str(generated_message.content),
                    message_category=MessageCategory.CONVERSATION.value
                )
                logger.info("Successfully persisted AI Text Message")
                
        except Exception as e:
            logger.error(f"Error in ImmediatePersistenceCallback on_chat_model_end: {e}", exc_info=True)

    async def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Run when tool ends running."""
        try:
            tool_name = kwargs.get('name', 'unknown_tool')
            
            # Skip tools that handle their own persistence or shouldn't be logged this way
            if tool_name.startswith('reply_to_user_'):
                return

            logger.info(f"Persisting tool result for {tool_name}")
            
            # Construct metadata
            metadata = {
                "tool_name": tool_name,
                "message_type": "tool_result",
                "tool_call_id": str(run_id) 
            }
            
            # Special case for async tasks (legacy support)
            if tool_name == "browse_website_with_ai":
                metadata["asynchronous_task_status"] = "requested"

            # Persist to database
            # We use TOOL_EXECUTION category so it's hidden from main view unless requested
            # but available for LLM context.
            await self.conversation_manager.add_assistant_message(
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                content=str(output),
                metadata=metadata,
                message_category=MessageCategory.TOOL_EXECUTION.value
            )
            logger.info(f"Successfully persisted tool output for {tool_name}")
            
        except Exception as e:
            logger.error(f"Error in ImmediatePersistenceCallback on_tool_end: {e}", exc_info=True)
