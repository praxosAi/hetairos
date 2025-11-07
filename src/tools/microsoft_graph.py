from typing import List
from langchain_core.tools import tool
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_outlook_tools(outlook_client: MicrosoftGraphIntegration, tool_registry) -> List:
    """Create Outlook-related tools"""

    @tool
    async def send_outlook_email(recipient: str, subject: str, body: str) -> ToolExecutionResponse:
        """Sends an email using Outlook."""
        try:
            await outlook_client.send_email(recipient, subject, body)
            return ToolExecutionResponse(status="success", result="Email sent successfully.")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="send_outlook_email",
                exception=e,
                integration="Microsoft Outlook",
                context={"recipient": recipient}
            )
    
    @tool 
    async def fetch_outlook_calendar_events(time_min: str, time_max: str) -> ToolExecutionResponse:
        """Fetches calendar events from Outlook."""
        try:
            events = await outlook_client.get_calendar_events(time_min, time_max)
            return ToolExecutionResponse(status="success", result=events)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="fetch_outlook_calendar_events",
                exception=e,
                integration="Microsoft Outlook"
            )

    @tool
    async def get_outlook_emails_from_sender(sender_email: str, max_results: int = 10) -> ToolExecutionResponse:
        """Fetches the most recent emails from a specific sender in the user's Outlook account."""
        try:
            emails = await outlook_client.get_emails_from_sender(sender_email, max_results)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_outlook_emails_from_sender",
                exception=e,
                integration="Microsoft Outlook",
                context={"sender_email": sender_email}
            )

    @tool
    async def find_outlook_contact_email(name: str) -> ToolExecutionResponse:
        """Searches the user's Outlook contacts for a person's email address by their name."""
        try:
            contacts = await outlook_client.find_contact_email(name)
            if not contacts:
                return ToolExecutionResponse(status="success", result=f"No contacts found matching the name '{name}'.")
            return ToolExecutionResponse(status="success", result=contacts)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="find_outlook_contact_email",
                exception=e,
                integration="Microsoft Outlook",
                context={"contact_name": name}
            )

    # Tool registry is passed in and already loaded
    all_tools = [
        send_outlook_email,
        fetch_outlook_calendar_events,
        get_outlook_emails_from_sender,
        find_outlook_contact_email
    ]

    # Apply descriptions from YAML database (single account integration)
    tool_registry.apply_descriptions_to_tools(all_tools)

    return all_tools
