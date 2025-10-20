from src.utils.logging.base_logger import setup_logger
from langchain.tools import AsyncCallbackHandler
logger = setup_logger(__name__)
from typing import Any, Dict
from datetime import datetime
from bson import ObjectId
import asyncio
from src.utils.database import db_manager
class ToolMonitorCallback(AsyncCallbackHandler):
    """Callback handler for monitoring tool usage and tracking milestones."""

    def __init__(self, user_id: str, execution_id: str):
        super().__init__()
        self.user_id = user_id
        self.execution_id = execution_id

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Called when a tool starts execution."""
        tool_name = serialized.get('name', 'unknown_tool')
        logger.info(f"[TOOL START] {tool_name} | User: {self.user_id} | Execution: {self.execution_id}")
        logger.debug(f"[TOOL INPUT] {tool_name}: {input_str[:200]}")

        # Track milestone in MongoDB - fire and forget (non-blocking)
        try:
            asyncio.create_task(self._track_tool_milestone(tool_name))
        except Exception as e:
            logger.error(f"Error creating milestone tracking task for {tool_name}: {e}", exc_info=True)

    async def on_tool_end(self, output: str, **kwargs) -> None:
        """Called when a tool completes successfully."""
        tool_name = kwargs.get('name', 'unknown_tool')
        output_preview = str(output)[:200] if output else "No output"
        logger.info(f"[TOOL END] {tool_name} | Output: {output_preview}")

    async def on_tool_error(self, error: Exception, **kwargs) -> None:
        """Called when a tool encounters an error."""
        tool_name = kwargs.get('name', 'unknown_tool')
        logger.error(f"[TOOL ERROR] {tool_name} | Error: {error}", exc_info=True)

    async def _track_tool_milestone(self, tool_name: str) -> None:
        """Track user tool usage milestone in MongoDB."""


        # Check if this is the first time user has called this tool
        existing = await db_manager.get_existing_tool_milestone(self.user_id, tool_name)

        now = datetime.utcnow()

        if not existing:
            # First time using this tool - create milestone
            milestone_doc = {
                "user_id": ObjectId(self.user_id),
                "tool_name": tool_name,
                "first_called_at": now,
                "last_called_at": now,
                "call_count": 1,
                "execution_ids": [self.execution_id]
            }
            await db_manager.insert_tool_milestone(milestone_doc)
            logger.info(f"[MILESTONE] User {self.user_id} first time using tool: {tool_name}")
        else:
            # Update existing milestone
            await db_manager.update_tool_milestone(self.user_id, tool_name,                {
                    "$set": {"last_called_at": now},
                    "$inc": {"call_count": 1},
                    "$addToSet": {"execution_ids": self.execution_id}
                })