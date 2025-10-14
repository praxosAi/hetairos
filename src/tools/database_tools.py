from datetime import datetime
from typing import List, Optional
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.database import conversation_db
from src.services.integration_service import integration_service
from enum import Enum
from src.utils.logging import setup_logger
def create_database_access_tools(user_id: str) -> list:
    """Create database access tools bound to a specific user_id."""
    logger = setup_logger('database_tools')
    @tool
    async def fetch_latest_messages(limit: int = 5) -> ToolExecutionResponse:
        """
        Fetches the latest messages for the user. do not use this for long term memory, use it if you are confused about most recent messages, or a message feels like it was part of a conversation recently.
        """
        try:
            # Placeholder for actual database fetching logic
            messages = await conversation_db.get_recent_messages(user_id=user_id, limit=limit)
            return ToolExecutionResponse(status="success", result=messages)
        except Exception as e:
            logger.error(f"Error fetching latest messages for user {user_id}: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="fetch_latest_messages",
                exception=e,
                integration="database"
            )
    @tool
    async def get_user_integration_records() -> ToolExecutionResponse:
        """
        Fetches the user's integration records from the database.
        """
        try:
            records = await integration_service.get_user_integrations_llm_info(user_id=user_id)
            return ToolExecutionResponse(status="success", result=records)
        except Exception as e:
            logger.error(f"Error fetching integration records for user {user_id}: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_user_integration_records",
                exception=e,
                integration="database"
            )
    ### TODO: media tool, and praxos call for media tool with source id
    return [fetch_latest_messages, get_user_integration_records]