from typing import List
from langchain_core.tools import tool
from src.integrations.email.gmail_client import GmailIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_email_tools() -> List:
    """Creates a list of mock tools related to email."""

    USER_MESSAGE = "Sorry, I can't have access to any email from your account. Please go the integeration page and connect your emial and then try again."

    @tool
    async def send_email(recipient: str, subject: str, body: str) -> ToolExecutionResponse:
        """Sends an email on behalf of user from the user's email"""
        return ToolExecutionResponse(status="misconfigured", user_message=USER_MESSAGE)

    @tool
    async def get_emails_from_sender(sender_email: str, max_results: int = 10) -> ToolExecutionResponse:
        """Fetches the most recent emails from a specific sender in the user's email."""
        return ToolExecutionResponse(status="misconfigured", user_message=USER_MESSAGE)

    @tool
    async def find_contact_email(name: str) -> ToolExecutionResponse:
        """Searches the user's contacts for a person's email address by their name."""
        return ToolExecutionResponse(status="misconfigured", user_message=USER_MESSAGE)
    
    return [send_email, get_emails_from_sender, find_contact_email]

def create_calendar_tools() -> List:
    """Creates mock calendar-related tools"""

    USER_MESSAGE = "Sorry, I can't have access to any calander from your account. Please go the integeration page and connect your calendar and then try again."

    @tool
    async def get_calendar_events(
        time_min: str,
        time_max: str
    ) -> ToolExecutionResponse:
        """Fetches events from the user's Calendar within a specified time window."""
        return ToolExecutionResponse(status="misconfigured", user_message=USER_MESSAGE)
    
    @tool
    async def create_calendar_event(
        title: str,
        start_time: str, 
        end_time: str,
        attendees: List[str] = [],
        description: str = "",
        location: str = "",
    ) -> ToolExecutionResponse:
        """Creates a new event on the user's Google Calendar."""
        return ToolExecutionResponse(status="misconfigured", user_message=USER_MESSAGE)
    
    return [get_calendar_events, create_calendar_event]
