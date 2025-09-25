from datetime import datetime
from typing import List, Optional
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.utils.database import conversation_db
from enum import Enum

def create_database_access_tools(user_id: str) -> list:
    """Create database access tools bound to a specific user_id."""
    @tool
    async def fetch_latest_messages(limit: int = 5, platform: str = None) -> ToolExecutionResponse:
        """
        Fetches the latest messages for the user. you may specify a platform, or leave it None to get from all platforms.
        """
        try:
            # Placeholder for actual database fetching logic
            messages = await conversation_db.get_recent_messages(user_id=user_id, limit=limit, platform=platform)
            return ToolExecutionResponse(status="success", result=messages)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Failed to fetch messages.")
