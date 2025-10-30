from datetime import datetime
from typing import List, Optional
from langchain_core.tools import tool
from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from src.utils.timezone_utils import to_utc,to_rfc3339
logger = setup_logger(__name__)

def create_calendar_tools(gcal_integration: GoogleCalendarIntegration,user_time_zone:str) -> List:
    """Creates calendar-related tools that are dynamically configured for single or multiple user accounts."""

    @tool
    async def get_calendar_events(
        time_min: datetime,
        time_max: datetime,
        max_results: int = 10,
        calendar_id: str = 'primary',
        account: Optional[str] = None  # Add optional account parameter
    ) -> ToolExecutionResponse:
        """Fetches events from the user's Google Calendar within a specified time window."""
        try:
            ### now, we must cast the timezones to the user's timezone

            # Pass the account parameter to the integration method
            time_max = to_rfc3339(to_utc(time_max,user_time_zone))
            time_min = to_rfc3339(to_utc(time_min,user_time_zone))
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
            return ErrorResponseBuilder.from_exception(
                operation="get_calendar_events",
                exception=e,
                integration="Google Calendar",
                context={"calendar_id": calendar_id, "account": account}
            )
    
    @tool
    async def create_calendar_event(
        title: str,
        start_time: datetime,
        end_time: datetime,
        attendees: List[str] = [],
        description: str = "",
        location: str = "",
        calendar_id: str = 'primary',
        account: Optional[str] = None,
        recurrence_rule: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new event on the user's Google Calendar.

        Args:
            title: Event title/summary
            start_time: Start time as datetime object
            end_time: End time as datetime object
            attendees: List of attendee email addresses
            description: Event description
            location: Event location
            calendar_id: Calendar ID (default: 'primary')
            account: Account email (for multi-account users)
            recurrence_rule: Optional RRULE string for recurring events (RFC 5545 format)
                            Examples:
                            - "FREQ=DAILY;COUNT=5" - Daily for 5 days
                            - "FREQ=WEEKLY;BYDAY=MO,WE,FR" - Every Monday, Wednesday, Friday
                            - "FREQ=MONTHLY;BYMONTHDAY=15" - 15th of every month
                            - "FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=1" - June 1st every year
                            - "FREQ=WEEKLY;INTERVAL=2" - Every 2 weeks
                            - "FREQ=DAILY;UNTIL=20251231T235959Z" - Daily until Dec 31, 2025

        Returns:
            Success status and event link

        Examples:
            # One-time event
            create_calendar_event("Team Meeting", start_time, end_time)

            # Daily standup for 30 days
            create_calendar_event("Daily Standup", start_time, end_time, recurrence_rule="FREQ=DAILY;COUNT=30")

            # Weekly meeting every Monday
            create_calendar_event("Weekly Review", start_time, end_time, recurrence_rule="FREQ=WEEKLY;BYDAY=MO")

            # Monthly team lunch on 1st Friday
            create_calendar_event("Team Lunch", start_time, end_time, recurrence_rule="FREQ=MONTHLY;BYDAY=1FR")
        """
        try:
            start_time = to_rfc3339(to_utc(start_time,user_time_zone))
            end_time = to_rfc3339(to_utc(end_time,user_time_zone))

            from src.utils.constant import NO_WATERMARK_USER_IDS
            signed_description = (description or "")
            if gcal_integration.user_id not in NO_WATERMARK_USER_IDS:
                signed_description += '\n\nSchedule directive created by <a href="https://app.mypraxos.com">My Praxos</a>'

            # Format recurrence rule if provided
            recurrence = None
            if recurrence_rule:
                # RRULE should be prefixed with "RRULE:" if not already
                if not recurrence_rule.startswith('RRULE:'):
                    recurrence_rule = f'RRULE:{recurrence_rule}'
                recurrence = [recurrence_rule]
                logger.info(f"Creating recurring event: {recurrence_rule}")

            # Pass the account parameter to the integration method
            created_event = await gcal_integration.create_calendar_event(
                title=title,
                start_time=start_time,
                end_time=end_time,
                attendees=attendees,
                description=signed_description,
                location=location,
                calendar_id=calendar_id,
                account=account,
                recurrence=recurrence
            )
            return ToolExecutionResponse(status="success", result=created_event)
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="create_calendar_event",
                exception=e,
                integration="Google Calendar",
                context={"title": title, "calendar_id": calendar_id, "account": account}
            )
    
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