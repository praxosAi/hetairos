from typing import List, Optional
from langchain_core.tools import tool
from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_calendar_tools(gcal_integration: GoogleCalendarIntegration) -> List:
    """Creates calendar-related tools that are dynamically configured for single or multiple user accounts."""

    @tool
    async def get_calendar_events(
        time_min: str,
        time_max: str,
        max_results: int = 10,
        calendar_id: str = 'primary',
        account: Optional[str] = None  # Add optional account parameter
    ) -> ToolExecutionResponse:
        """Fetches events from the user's Google Calendar within a specified time window."""
        try:
            # Pass the account parameter to the integration method
            events = await gcal_integration.get_calendar_events(
                time_min=time_min,
                time_max=time_max,
                max_results=max_results,
                calendar_id=calendar_id,
                account=account
            )
            if not events:
                return ToolExecutionResponse(status="success", result='No events found in that time frame.')
            return ToolExecutionResponse(status="success", result=events)
        except Exception as e:
            logger.error(f"Error fetching calendar events: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="There was an error fetching calendar events.")
    
    @tool
    async def create_calendar_event(
        title: str,
        start_time: str, 
        end_time: str,
        attendees: List[str] = [],
        description: str = "",
        location: str = "",
        calendar_id: str = 'primary',
        account: Optional[str] = None  # Add optional account parameter
    ) -> ToolExecutionResponse:
        """Creates a new event on the user's Google Calendar."""
        try:
            signed_description = (description or "") + '\n\nSchedule directive created by <a href="https://app.mypraxos.com">My Praxos</a>'
            # Pass the account parameter to the integration method
            created_event = await gcal_integration.create_calendar_event(
                title=title,
                start_time=start_time,
                end_time=end_time,
                attendees=attendees,
                description=signed_description,
                location=location,
                calendar_id=calendar_id,
                account=account
            )
            return ToolExecutionResponse(status="success", result=created_event)
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="There was an error creating the calendar event.")
    
    # --- Dynamically configure tool descriptions ---
    
    accounts = gcal_integration.get_connected_accounts()
    if not accounts:
        return [] # Return no tools if no accounts are authenticated

    all_tools = [get_calendar_events, create_calendar_event]

    if len(accounts) == 1:
        # If there's only one account, mention it in the description for context.
        user_email = accounts[0]
        for t in all_tools:
            t.description += f" The user's connected calendar account is {user_email}."
    else:
        # If there are multiple, instruct the AI that it MUST specify which account to use.
        account_list_str = ", ".join(f"'{acc}'" for acc in accounts)
        for t in all_tools:
            t.description += (
                f" The user has multiple calendar accounts. You MUST use the 'account' parameter to specify which one to use. "
                f"Available accounts are: [{account_list_str}]."
            )
            
    return all_tools