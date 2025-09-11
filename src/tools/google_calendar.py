from typing import List
from langchain_core.tools import tool
from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_calendar_tools(gcal_integration: GoogleCalendarIntegration) -> List:
    """Creates calendar-related tools using the GoogleCalendarIntegration client."""

    calender_info = gcal_integration.get_calendar_owner_info()
    user_email=calender_info.get('summary', '')

    @tool
    async def get_calendar_events(
        time_min: str,
        time_max: str,
        max_results: int = 10,
        calendar_id: str = 'primary'
    ) -> ToolExecutionResponse:
        """Fetches events from the user's Google Calendar ({user_email}) within a specified time window."""
        try:
            logger.info(f"Fetching calendar events for {user_email} with calendar_id: {calendar_id}, time_min: {time_min}, time_max: {time_max}, max_results: {max_results}")
            events = await gcal_integration.get_calendar_events(time_min, time_max, max_results, calendar_id)
            if not events:
                return ToolExecutionResponse(status="success", result='No events found.')
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
        calendar_id: str = 'primary'
    ) -> ToolExecutionResponse:
        """Creates a new event on the user's Google Calendar ({user_email})."""
        try:
            signed_description = (description if description else "") + '\n\nSchedule directive created by <a href="https://app.mypraxos.com/log-in">My Praxos</a>'
            created_event = await gcal_integration.create_calendar_event(title, start_time, end_time, attendees, signed_description, location, calendar_id)
            return ToolExecutionResponse(status="success", result=created_event)
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))
    
    get_calendar_events.description = get_calendar_events.description.format(user_email=user_email)
    create_calendar_event.description = create_calendar_event.description.format(user_email=user_email)
    return [get_calendar_events, create_calendar_event]
