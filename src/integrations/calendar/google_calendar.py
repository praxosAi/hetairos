import asyncio
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from src.integrations.base_integration import BaseIntegration
from src.config.settings import settings
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)

class GoogleCalendarIntegration(BaseIntegration):
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.service = None
        self.credentials = None
        self.calendar_info = None
    
    async def authenticate(self) -> bool:
        """Authenticate with Google Calendar API using user-specific tokens."""
        try:
            self.credentials = await integration_service.create_google_credentials(self.user_id, 'google_calendar')
            if not self.credentials:
                logger.error(f"Failed to create Google Calendar credentials for user {self.user_id}")
                return False
            
            self.service = build('calendar', 'v3', credentials=self.credentials)
            return True
        except Exception as e:
            logger.error(f"Google Calendar authentication failed for user {self.user_id}: {e}")
            return False
    
    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch calendar events since last sync"""
        if not self.service:
            return []
        
        try:
            # Default to events from 7 days ago if no since timestamp
            if since is None:
                since = datetime.utcnow() - timedelta(days=7)
            
            # Fetch events
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=since.isoformat() + 'Z',
                maxResults=50,  # Limit for testing
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Convert to standardized format
            formatted_events = []
            for event in events:
                formatted_event = {
                    "id": event['id'],
                    "title": event.get('summary', 'No Title'),
                    "start": event.get('start', {}).get('dateTime', event.get('start', {}).get('date')),
                    "end": event.get('end', {}).get('dateTime', event.get('end', {}).get('date')),
                    "description": event.get('description', ''),
                    "location": event.get('location', ''),
                    "attendees": [attendee.get('email') for attendee in event.get('attendees', [])],
                    "source": "google_calendar",
                    "created": event.get('created'),
                    "updated": event.get('updated')
                }
                formatted_events.append(formatted_event)
            
            return formatted_events
            
        except Exception as e:
            print(f"Error fetching Google Calendar events: {e}")
            return []

    def _remove_timezone_offset(self, time_string: str) -> str:
        """Remove timezone offset from a time string"""
        if 'T' in time_string and len(time_string.split('-')) >= 4:
            return time_string.rsplit('-', 1)[0]
        return time_string

    async def get_calendar_events(self, time_min: str, time_max: str, max_results: int = 10, calendar_id: str = 'primary') -> List[Dict]:
        """Fetches events from Google Calendar."""
        if not self.service:
            raise Exception("Google Calendar service not initialized. Call authenticate() first.")
        
        params = {
            'calendarId': calendar_id,
            'maxResults': max_results,
            'singleEvents': True,
            'orderBy': 'startTime',
            'timeMin': self._remove_timezone_offset(time_min) + '-04:00',
            'timeMax': self._remove_timezone_offset(time_max) + '-04:00'
        }
        
        events_result = self.service.events().list(**params).execute()
        items = events_result.get('items', [])
        
        formatted_events = []
        for event in items:
            formatted_events.append({
                'title': event.get('summary', 'No Title'),
                'start': event.get('start', {}).get('dateTime', event.get('start', {}).get('date')),
                'end': event.get('end', {}).get('dateTime', event.get('end', {}).get('date')),
                'description': event.get('description', '')[:100] + '...' if event.get('description') else 'No description'
            })
        return formatted_events

    def get_calendar_owner_info(self) -> Dict:
        """Gets the primary calendar owner information."""
        if self.calendar_info:
            return self.calendar_info

        if not self.service:
            raise Exception("Google Calendar service not initialized. Call authenticate() first.")
        
        try:
            calendar = self.service.calendars().get(calendarId='primary').execute()
            self.calendar_info = {
                'summary': calendar.get('summary', ''),  # Usually the user's email
                'description': calendar.get('description', ''),
                'timezone': calendar.get('timeZone', ''),
                'id': calendar.get('id', '')
            }
            return self.calendar_info
        except Exception as e:
            logger.error(f"Error fetching calendar owner info: {e}")
            raise Exception(f"Failed to get calendar owner info: {e}")

    async def create_calendar_event(self, title: str, start_time: str, end_time: str, attendees: List[str] = [], description: str = "", location: str = "", calendar_id: str = 'primary') -> Dict:
        """Creates a new event on Google Calendar."""
        if not self.service:
            raise Exception("Google Calendar service not initialized. Call authenticate() first.")

        start_time = self._remove_timezone_offset(start_time)
        end_time = self._remove_timezone_offset(end_time)
        event_body = {
            'summary': title,
            'location': location,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': 'America/New_York'},
            'end': {'dateTime': end_time, 'timeZone': 'America/New_York'},
            'attendees': [{'email': email} for email in attendees] if attendees else [],
            'reminders': {'useDefault': True},
        }
        
        created_event = self.service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            sendUpdates='all'
        ).execute()
        
        return {"event_link": created_event.get('htmlLink')}