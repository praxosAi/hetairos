import asyncio
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Optional,Any, Tuple
import aiohttp
import mimetypes
from src.integrations.base_integration import BaseIntegration
from src.config.settings import settings
from src.utils.rate_limiter import rate_limiter
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from src.utils.database import db_manager
from src.utils.blob_utils import upload_bytes_to_blob_storage
from bson import ObjectId
import re
logger = setup_logger(__name__)

class MicrosoftGraphIntegration(BaseIntegration):
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.access_token = None
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"
        
    async def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API, refreshing the token if necessary."""
        try:
            token_info = await integration_service.get_integration_token(self.user_id, 'outlook')
            if not token_info:
                logger.error(f"Failed to retrieve Microsoft token for user {self.user_id}")
                return False

            # Check if the token is expired or close to expiring (e.g., within 5 minutes)
            expires_at = token_info.get('token_expiry')
            if not expires_at or (expires_at - datetime.utcnow()) < timedelta(minutes=5):
                logger.info(f"Microsoft token for user {self.user_id} is expired or nearing expiry. Refreshing.")
                new_token_info = await self._refresh_token(token_info.get('refresh_token'))
                if not new_token_info:
                    logger.error(f"Failed to refresh Microsoft token for user {self.user_id}")
                    return False
                self.access_token = new_token_info['access_token']
            else:
                self.access_token = token_info['access_token']
            
            return True
        except Exception as e:
            logger.error(f"Microsoft Graph authentication failed for user {self.user_id}: {e}", exc_info=True)
            return False

    async def _refresh_token(self, refresh_token: str) -> Optional[Dict]:
        """Refreshes the Microsoft access token using the refresh token."""
        if not refresh_token:
            logger.error("No refresh token available to refresh the Microsoft access token.")
            return None

        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        payload = {
            'client_id': settings.MICROSOFT_CLIENT_ID,
            'scope': 'offline_access user.read mail.readwrite mail.send calendars.readwrite',
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
            'client_secret': settings.MICROSOFT_CLIENT_SECRET,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=payload) as response:
                    response.raise_for_status()
                    new_token_data = await response.json()

            # Prepare the new token information to be stored
            new_token_info = {
                'access_token': new_token_data['access_token'],
                'refresh_token': new_token_data['refresh_token'], # Microsoft often returns a new refresh token
                'token_expiry': datetime.utcnow() + timedelta(seconds=new_token_data['expires_in']),
            }

            # Save the new tokens to the database
            await integration_service.update_integration_token_and_refresh_token(
                user_id=self.user_id, 
                integration_name='outlook', 
                new_token=new_token_info['access_token'],
                new_expiry=new_token_info['token_expiry'],
                new_refresh_token=new_token_info['refresh_token']
            )

            logger.info(f"Successfully refreshed and updated Microsoft token for user {self.user_id}")
            return new_token_info
        except aiohttp.ClientError as e:
            logger.error(f"Error refreshing Microsoft token: {e}", exc_info=True)
            return None
    
    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent emails and calendar events from Microsoft Graph."""
        if not self.access_token:
            return []
        
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)
        
        # Fetch both emails and calendar events
        emails = await self._fetch_emails(since)
        events = await self._fetch_calendar_events(since)
        
        return emails + events

    async def _fetch_emails(self, since: datetime) -> List[Dict]:
        """Fetch recent emails from Outlook."""
        since_str = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        params = {
            "$filter": f"receivedDateTime ge {since_str}",
            "$top": settings.MAX_EMAILS,
            "$orderby": "receivedDateTime desc",
            "$expand": "attachments"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.graph_endpoint}/me/messages", headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
            
            messages = data.get('value', [])
            formatted_messages = [await self._format_message(msg) for msg in messages]
            return formatted_messages
        except Exception as e:
            logger.error(f"Error fetching Outlook messages: {e}")
            return []

    async def _fetch_calendar_events(self, since: datetime) -> List[Dict]:
        """Fetch recent calendar events."""
        since_str = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        params = {
            "$filter": f"start/dateTime ge '{since_str}'",
            "$top": 100,
            "$orderby": "start/dateTime asc"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.graph_endpoint}/me/calendar/events", headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()

            events = data.get('value', [])
            formatted_events = [self._format_event(event) for event in events]
            return formatted_events
        except Exception as e:
            logger.error(f"Error fetching Outlook Calendar events: {e}")
            return []

    def _format_event(self, event: Dict) -> Dict:
        """Formats a calendar event into a standardized dictionary."""
        return {
            "id": event.get("id"),
            "type": "calendar_event",
            "title": event.get("subject", "No Title"),
            "start": event.get("start", {}).get("dateTime"),
            "end": event.get("end", {}).get("dateTime"),
            "description": event.get("body", {}).get("content", ""),
            "location": event.get("location", {}).get("displayName", ""),
            "attendees": [att.get("emailAddress", {}).get("address") for att in event.get("attendees", [])],
            "source": "outlook_calendar"
        }

    async def _format_message(self, message: Dict) -> Dict:
        """Format Outlook message into standardized format"""
        return {
            "id": message['id'],
            "type": "email",
            "subject": message.get('subject', 'No Subject'),
            "from": message.get('from', {}).get('emailAddress', {}).get('address', ''),
            "to": [recipient.get('emailAddress', {}).get('address', '') for recipient in message.get('toRecipients', [])],
            "date": message.get('receivedDateTime', ''),
            "body": message.get('body', {}).get('content', ''),
            "attachments": self._format_attachments(message.get('attachments', [])),
            "source": "outlook"
        }
    
    def _format_attachments(self, attachments: List[Dict]) -> List[Dict]:
        """Format attachment information"""
        return [{
            "id": att['id'],
            "name": att.get('name', ''),
            "contentType": att.get('contentType', ''),
            "size": att.get('size', 0)
        } for att in attachments]
    
    async def download_attachment(self, message_id: str, attachment_id: str) -> Optional[bytes]:
        """Download attachment from Outlook"""
        if not self.access_token: return None
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.graph_endpoint}/me/messages/{message_id}/attachments/{attachment_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    attachment_data = await response.json()
            if 'contentBytes' in attachment_data:
                return base64.b64decode(attachment_data['contentBytes'])
            return None
        except Exception as e:
            logger.error(f"Error downloading attachment: {e}")
            return None

    async def send_email(self, recipient: str, subject: str, body: str) -> Dict:
        """Send an email using Microsoft Graph API"""
        if not self.access_token:
            logger.error(f"Not authenticated to send email")
            raise Exception("Not authenticated")
        logger.info(f"Sending email to {recipient} with subject {subject} and body {body}")
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        email_data = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": recipient}}]
            },
            "saveToSentItems": "true"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.graph_endpoint}/me/sendMail", headers=headers, json=email_data) as response:
                    response.raise_for_status()
                    result = await response.text()
                    logger.info(f"Email sent successfully: {result}")
                    return result
        except Exception as e:
            logger.error(f"Error sending Outlook email: {e}",exc_info=True)
            raise

    async def get_calendar_events(self, time_min: str, time_max: str) -> List[Dict]:
        """Get calendar events within a specified time window."""
        logger.info(f"Getting calendar events from {time_min} to {time_max}")
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        params = {
            "startDateTime": time_min,
            "endDateTime": time_max,
            "$top": 100,
            "$orderby": "start/dateTime asc"
        }
        logger.info(f"Params: {params}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.graph_endpoint}/me/calendarview", headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
            events = data.get('value', [])
            return [self._format_event(event) for event in events]
        except Exception as e:
            logger.error(f"Error fetching Outlook Calendar events: {e}")
            return []

    async def get_event_by_id(self, event_id: str) -> Optional[Dict]:
        """Fetch a single calendar event by ID."""
        if not self.access_token:
            logger.error("Not authenticated to fetch event")
            return None

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.graph_endpoint}/me/events/{event_id}", headers=headers) as response:
                    response.raise_for_status()
                    event = await response.json()
            return self._format_event(event)
        except Exception as e:
            logger.error(f"Error fetching event {event_id}: {e}", exc_info=True)
            return None

    async def create_calendar_event(self, title: str, start_time: str, end_time: str, attendees: Optional[List[str]] = None, description: str = "", location: str = "") -> Dict:
        """Creates a new event on the user's primary calendar."""
        if not self.access_token:
            raise Exception("Not authenticated")

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        event_data = {
            "subject": title,
            "body": {"contentType": "HTML", "content": description},
            "start": {"dateTime": start_time, "timeZone": "UTC"},
            "end": {"dateTime": end_time, "timeZone": "UTC"},
            "location": {"displayName": location},
            "attendees": [{"emailAddress": {"address": email}, "type": "required"} for email in attendees] if attendees else []
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.graph_endpoint}/me/events", headers=headers, json=event_data) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Error creating Outlook Calendar event: {e}")
            raise

    async def get_emails_from_sender(self, sender_email: str, max_results: int = 10) -> List[Dict]:
        """Fetches the most recent emails from a specific sender."""
        if not self.access_token:
            raise Exception("Not authenticated")
        
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        params = {
            "$filter": f"from/emailAddress/address eq '{sender_email}'",
            "$top": max_results,
            "$orderby": "receivedDateTime desc"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.graph_endpoint}/me/messages", headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
            
            messages = data.get('value', [])
            return [await self._format_message(msg) for msg in messages]
        except Exception as e:
            logger.error(f"Error fetching emails from sender {sender_email}: {e}", exc_info=True)
            return []

    async def find_contact_email(self, name: str) -> List[Dict]:
        """Searches the user's contacts for a person's email address by their name."""
        if not self.access_token:
            raise Exception("Not authenticated")

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        params = {
            "$search": f'"{name}"',
            "$select": "displayName,emailAddresses"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.graph_endpoint}/me/contacts", headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()

            contacts = data.get('value', [])
            contact_list = []
            for contact in contacts:
                emails = contact.get('emailAddresses', [])
                if emails:
                    contact_list.append({
                        "name": contact.get('displayName', 'N/A'),
                        "email": emails[0].get('address', 'N/A')
                    })
            return contact_list
        except Exception as e:
            logger.error(f"Error searching for contact '{name}': {e}", exc_info=True)
            return []

    
    async def _graph_get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            return r.json()

    async def get_message_with_attachments(
        self,
        *,
        ms_user_id: str,
        message_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch a message with inline expanded attachments.
        (If your tenant disallows $expand, you can GET /attachments separately.)
        """
        url = f"{self.GRAPH_BASE}/users/{ms_user_id}/messages/{message_id}"
        params = {
            # Select only the fields you need
            "$select": "id,subject,body,from,toRecipients,receivedDateTime,conversationId,webLink,internetMessageHeaders",
            # Expand attachments (file + item + reference; file attachments have `contentBytes`)
            "$expand": "attachments($select=id,name,contentType,size,isInline,contentBytes)"
        }
        return await self._graph_get(url, params)

    def _ms_headers_to_map(self, headers: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
        m: Dict[str, str] = {}
        for h in headers or []:
            name = (h.get("name") or "").strip()
            value = (h.get("value") or "").strip()
            if name:
                m[name] = value
        return m

    def _extract_plain_text(self, body: Dict[str, Any]) -> str:
        """
        Outlook returns body as {contentType: 'html'|'text', content: '...'}
        Normalize to text (strip HTML crud in the simple case).
        """
        ctype = (body.get("contentType") or "").lower()
        content = body.get("content") or ""
        if ctype == "text":
            return content
        # super-minimal HTML -> text
        import re
        from html import unescape
        text = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
        text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return unescape(text).strip()

    async def _store_attachment(
        self,
        *,
        user_record: Dict[str, Any],
        message_id: str,
        att: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Store a *file* attachment (not item/reference) that has contentBytes.
        """
        content_bytes_b64 = att.get("contentBytes")
        if not content_bytes_b64:
            return None

        raw = base64.b64decode(content_bytes_b64.encode("utf-8"))

        filename = att.get("name") or "attachment"
        mime_type = att.get("contentType") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        blob_name = f"{str(user_record['_id'])}/outlook/{message_id}/{filename}"
        blob_path = await upload_bytes_to_blob_storage(raw, blob_name, content_type=mime_type)

        # Insert into documents; you already use platform_message_id as the email id
        document_entry = {
            "user_id": ObjectId(user_record["_id"]),
            "platform": "outlook",
            "platform_file_id": att.get("id"),
            "platform_message_id": message_id,
            "type": "document",
            "blob_path": blob_name,
            "mime_type": mime_type,
            "file_name": filename,
        }
        inserted_id = await db_manager.add_document(document_entry)

        return {
            "type": "document",
            "blob_path": blob_path,
            "mime_type": mime_type,
            "caption": "",
            "file_name": filename,
            "inserted_id": str(inserted_id),
        }

    async def normalize_message_for_ingestion(
        self,
        *,
        user_record: Dict[str, Any],
        ms_user_id: str,
        message_id: str,
        command_prefix: str = "",
    ) -> Dict[str, Any]:
        """
        Fetch + normalize an Outlook message into your standard shape:
          payload.text, payload.files[], and metadata.
        """
        msg = await self.get_message_with_attachments(ms_user_id=ms_user_id, message_id=message_id)

        headers_map = self._ms_headers_to_map(msg.get("internetMessageHeaders"))

        body_text = self._extract_plain_text(msg.get("body") or {})
        if command_prefix:
            body_text = f"{command_prefix}\n\n{body_text}" if body_text else command_prefix

        files: List[Dict[str, Any]] = []
        for a in msg.get("attachments") or []:
            # Only store real file attachments with contentBytes
            if a.get("@odata.type", "").endswith("FileAttachment") and a.get("contentBytes"):
                file_rec = await self._store_attachment(
                    user_record=user_record,
                    message_id=msg["id"],
                    att=a,
                )
                if file_rec:
                    files.append(file_rec)

        normalized = {
            "id": msg.get("id"),
            "thread_id": msg.get("conversationId"),
            "subject": msg.get("subject") or "No Subject",
            "from": (msg.get("from") or {}).get("emailAddress", {}).get("address", ""),
            "to": ", ".join([(r.get("emailAddress") or {}).get("address", "") for r in msg.get("toRecipients") or [] if r.get("emailAddress")]),
            "date": msg.get("receivedDateTime"),
            "timestamp": msg.get("receivedDateTime"),
            "labels": [],  # Outlook doesn't have Gmail-style labels; keep empty or map categories if you use them
            "snippet": "",  # You can synthesize a snippet if you want
            "payload": {
                "text": body_text,
                "files": files,
            },
            "metadata": {
                "platform": "outlook",
                "outlook_message_id": msg.get("id"),
                "outlook_thread_id": msg.get("conversationId"),
                "headers": headers_map,
                "web_link": msg.get("webLink"),
            },
        }
        return normalized
    
def extract_ms_ids_from_resource(resource: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (ms_user_id, message_id) given a resource like:
    /users/{ms_user_id}/messages/{message_id}
    /users/{ms_user_id}/mailFolders('Inbox')/messages/{message_id}
    """
    if not resource:
        return None, None
    m = re.search(r"users/([^/]+)/messages/([^/?]+)", resource)
    if m:
        return m.group(1), m.group(2)
    m2 = re.search(r"users/([^/]+)/mailFolders\('[^']+'\)/messages/([^/?]+)", resource)
    if m2:
        return m2.group(1), m2.group(2)
    return None, None