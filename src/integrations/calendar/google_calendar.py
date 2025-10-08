import asyncio
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from src.integrations.base_integration import BaseIntegration
from src.config.settings import settings
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger
from typing import Any, Dict, List, Optional, Tuple
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta


logger = setup_logger('google_calendar_client')

class GoogleCalendarIntegration(BaseIntegration):
    
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.services: Dict[str, Any] = {}
        self.credentials: Dict[str, Any] = {}
        self.connected_accounts: List[str] = []
        # A cache for calendar timezones to avoid repeated API calls
        self._timezone_cache: Dict[str, str] = {}


    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """
        Fetches calendar events since a given timestamp for syncing purposes.
        Defaults to the single connected account if available.
        """
        service, resolved_account = self._get_service_for_account(account)
        
        try:
            # Default to events from the last 7 days if no 'since' timestamp is provided
            if since is None:
                since = datetime.utcnow() - timedelta(days=7)
            
            # Format for the Google Calendar API (RFC3339 timestamp)
            time_min = since.isoformat() + 'Z'
            
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                maxResults=250,  # A reasonable limit for a sync operation
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Convert to a standardized format
            formatted_events = []
            for event in events:
                # Filter out attendees without an email address
                attendees = [
                    attendee['email'] 
                    for attendee in event.get('attendees', []) 
                    if 'email' in attendee
                ]
                
                formatted_event = {
                    "id": event['id'],
                    "title": event.get('summary', 'No Title'),
                    "start": event.get('start', {}).get('dateTime', event.get('start', {}).get('date')),
                    "end": event.get('end', {}).get('dateTime', event.get('end', {}).get('date')),
                    "description": event.get('description', ''),
                    "location": event.get('location', ''),
                    "attendees": attendees,
                    "source": "google_calendar",
                    "created": event.get('created'),
                    "updated": event.get('updated')
                }
                formatted_events.append(formatted_event)
            
            return formatted_events
            
        except Exception as e:
            logger.error(f"Error fetching Google Calendar events for {resolved_account}: {e}")
            return []

    async def authenticate(self) -> bool:
        """Authenticates all connected Google Calendar accounts for the user."""
        logger.info(f"Authenticating all Google Calendar accounts for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(self.user_id, 'google_calendar')

        if not integration_records:
            logger.warning(f"No Google Calendar integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record and record.get("connected_account")
        ]
        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict[str, Any]) -> bool:
        """Authenticates a single account and stores its service instance."""
        account_email = integration_record.get('connected_account')
        integration_id = integration_record.get('_id')
        creds = await integration_service.create_google_credentials(self.user_id, 'google_calendar', integration_id=integration_id)

        if not creds:
            logger.error(f"Failed to create credentials for calendar account {account_email}")
            return False

        try:
            service = build('calendar', 'v3', credentials=creds)
            self.services[account_email] = service
            self.credentials[account_email] = creds
            if account_email not in self.connected_accounts:
                self.connected_accounts.append(account_email)
            logger.info(f"Successfully authenticated calendar for {account_email}")
            return True
        except Exception as e:
            logger.error(f"Error building service for calendar account {account_email}: {e}")
            return False

    def get_connected_accounts(self) -> List[str]:
        """Returns a list of successfully authenticated calendar accounts."""
        return self.connected_accounts

    def _get_service_for_account(self, account: Optional[str] = None) -> Tuple[Any, str]:
        """Retrieves the correct service instance and resolved account email."""
        if account:
            service = self.services.get(account)
            if not service:
                raise ValueError(f"Account '{account}' is not authenticated or does not exist.")
            return service, account
        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.services[default_account], default_account
        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Google Calendar accounts found.")
        raise ValueError(f"Multiple accounts exist. Specify one with the 'account' parameter: {self.connected_accounts}")

    async def _get_calendar_timezone(self, service: Any, calendar_id: str) -> str:
        try:
            calendar = service.calendars().get(calendarId=calendar_id).execute()
            timezone = calendar.get('timeZone', 'UTC')

            return timezone
        except HttpError:
            logger.warning(f"Could not fetch timezone for calendar '{calendar_id}'. Defaulting to UTC.")
            return 'UTC'

    async def get_calendar_events(self, time_min: str, time_max: str, *, max_results: int = 10, calendar_id: str = 'primary', account: Optional[str] = None) -> List[Dict]:
        """Fetches events from a specific Google Calendar account."""
        service, resolved_account = self._get_service_for_account(account)
        logger.info(f"Fetching events from calendar '{calendar_id}' for account '{resolved_account}' between {time_min} and {time_max}")
        
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime',
                timeMin=time_min,
                timeMax=time_max
            ).execute()
            
            items = events_result.get('items', [])
            return [{
                'title': event.get('summary', 'No Title'),
                'start': event.get('start', {}).get('dateTime', event.get('start', {}).get('date')),
                'end': event.get('end', {}).get('dateTime', event.get('end', {}).get('date')),
                'description': event.get('description', 'No description')
            } for event in items]
        except HttpError as e:
            logger.error(f"Error fetching calendar events for {resolved_account}: {e}", exc_info=True)
            raise Exception("An error occurred while fetching calendar events.") from e

    async def create_calendar_event(self, title: str, start_time: str, end_time: str, *, attendees: List[str] = [], description: str = "", location: str = "", calendar_id: str = 'primary', account: Optional[str] = None) -> Dict:
        """Creates a new event on a specific Google Calendar account."""
        service, resolved_account = self._get_service_for_account(account)
        
        # Dynamically get the calendar's timezone for accurate event creation
        timezone = await self._get_calendar_timezone(service, calendar_id)
        
        event_body = {
            'summary': title,
            'location': location,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': timezone},
            'end': {'dateTime': end_time, 'timeZone': timezone},
            'attendees': [{'email': email} for email in attendees],
            'reminders': {'useDefault': True},
        }
        
        try:
            created_event = service.events().insert(
                calendarId=calendar_id,
                body=event_body,
                sendUpdates='all'
            ).execute()
            return {"status": "success", "event_link": created_event.get('htmlLink')}
        except HttpError as e:
            logger.error(f"Error creating event for {resolved_account}: {e}", exc_info=True)
            raise Exception("An error occurred while creating the calendar event.") from e