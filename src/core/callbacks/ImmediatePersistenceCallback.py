
from langchain_core.callbacks.base import BaseCallbackHandler, AsyncCallbackHandler
from typing import Any, Dict, List, Optional
from uuid import UUID
from src.utils.logging import setup_logger
from src.core.models import MessageCategory
import pymongo
from src.config.settings import settings
from datetime import datetime
from bson import ObjectId
import asyncio

logger = setup_logger(__name__)

class ImmediatePersistenceCallback(AsyncCallbackHandler):
    """
    Callback handler to immediately persist tool execution results to the database.
    Uses synchronous PyMongo in a thread pool to avoid asyncio loop mismatch errors.
    """

    def __init__(self, conversation_id: str, user_id: str, conversation_manager=None):
        self.conversation_id = conversation_id
        self.user_id = user_id
        # We create a sync client on the fly or could share one if carefully managed.
        # Creating one per event is safe for low volume, but for production, a global sync client is better.
        # For now, let's create a global-ish sync client pattern or just new connection.
        self.connection_string = settings.MONGO_CONNECTION_STRING
        self.db_name = settings.MONGO_DB_NAME

    def _persist_sync(self, content: str, metadata: Dict, message_category: str):
        """Synchronous DB insertion"""
        client = None
        try:
            client = pymongo.MongoClient(self.connection_string)
            db = client[self.db_name]
            messages_col = db["messages"]
            conversations_col = db["conversations"]
            
            message_doc = {
                "conversation_id": ObjectId(self.conversation_id),
                "user_id": ObjectId(self.user_id),
                "role": "assistant",
                "content": content,
                "message_type": "text",
                "message_category": message_category,
                "metadata": metadata,
                "timestamp": datetime.utcnow()
            }
            
            messages_col.insert_one(message_doc)
            
            # Update last activity
            conversations_col.update_one(
                {"_id": ObjectId(self.conversation_id)},
                {"$set": {"last_activity": datetime.utcnow()}}
            )
            logger.info("Successfully persisted message via sync callback")
            
        except Exception as e:
            logger.error(f"Sync persistence failed: {e}", exc_info=True)
        finally:
            if client:
                client.close()

    async def on_chat_model_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Run when LLM ends running."""
        try:
            if not response.generations or not response.generations[0]:
                return
                
            generated_message = response.generations[0][0].message
            loop = asyncio.get_running_loop()
            
            if hasattr(generated_message, 'tool_calls') and generated_message.tool_calls:
                logger.info(f"Persisting AI Message with {len(generated_message.tool_calls)} tool calls")
                content = generated_message.content if generated_message.content else ""
                metadata = {"tool_calls": [tc for tc in generated_message.tool_calls]}
                
                await loop.run_in_executor(
                    None, 
                    self._persist_sync, 
                    str(content), 
                    metadata, 
                    MessageCategory.TOOL_EXECUTION.value
                )
            
            elif generated_message.content:
                logger.info("Persisting AI Text Message")
                metadata = {}
                await loop.run_in_executor(
                    None, 
                    self._persist_sync, 
                    str(generated_message.content), 
                    metadata, 
                    MessageCategory.CONVERSATION.value
                )
                
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
            logger.info(f"ImmediatePersistenceCallback received tool end for {tool_name}, with output {output}")
            ### actually, it should be persisted for recording purposes, just not sent to user if messaging tool
            if tool_name.startswith('reply_to_user_'):
                return

            logger.info(f"Persisting tool result for {tool_name}")
            
            metadata = {
                "tool_name": tool_name,
                "message_type": "tool_result",
                "tool_call_id": str(run_id) 
            }
            
            if tool_name == "browse_website_with_ai":
                metadata["asynchronous_task_status"] = "requested"

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, 
                self._persist_sync, 
                str(output), 
                metadata, 
                MessageCategory.TOOL_EXECUTION.value
            )
            
        except Exception as e:
            logger.error(f"Error in ImmediatePersistenceCallback on_tool_end: {e}", exc_info=True)
