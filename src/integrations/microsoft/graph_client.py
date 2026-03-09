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
from urllib.parse import urlencode,quote
import httpx
import json
import re
logger = setup_logger(__name__)
PREFER_IMMUTABLE_ID = {'Prefer': 'IdType="ImmutableId"'}

class GraphBatchQueue:
    """
    Singleton queue manager to handle Microsoft Graph API rate limits.
    Graph API supports $batch with max 20 requests per batch.
    To stay under typical limits, we throttle to 1 batch every 0.2s (~100 req/sec).
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GraphBatchQueue, cls).__new__(cls)
            cls._instance.queue = asyncio.Queue()
            cls._instance._worker_task = None
            cls._instance._session = None # Used to reuse connection pool for batch worker
        return cls._instance

    async def enqueue_request(self, access_token: str, method: str, url: str, headers: Dict[str, str] = None, body: Dict = None) -> Any:
        future = asyncio.Future()
        
        # Strip the base graph endpoint if present, $batch requires relative paths
        if url.startswith("https://graph.microsoft.com/v1.0"):
            url = url.replace("https://graph.microsoft.com/v1.0", "")
            
        req_obj = {
            "method": method,
            "url": url,
            "headers": headers or {"Content-Type": "application/json"},
            "access_token": access_token,
            "future": future
        }
        if body is not None:
            req_obj["body"] = body
            
        await self.queue.put(req_obj)
        
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())
            
        return await future

    async def _process_queue(self):
        self._session = aiohttp.ClientSession()
        try:
            while True:
                # Group by access token (different users can't share a $batch payload)
                batch_by_token = {}
                queued_items = []
                
                # Try to pull up to 20 items off the queue
                for _ in range(20):
                    if self.queue.empty(): break
                    item = await self.queue.get()
                    queued_items.append(item)
                    
                if not queued_items:
                    # Queue is empty, sleep briefly then check again
                    await asyncio.sleep(0.1)
                    continue
                    
                # Organize by token
                for item in queued_items:
                    token = item["access_token"]
                    if token not in batch_by_token:
                        batch_by_token[token] = []
                    batch_by_token[token].append(item)

                # Process batches
                for token, items in batch_by_token.items():
                    # If somehow a single token has > 20, split it (shouldn't happen given the loop above, but safe)
                    for i in range(0, len(items), 20):
                        chunk = items[i:i+20]
                        batch_requests = []
                        for idx, req in enumerate(chunk):
                            batch_req = {
                                "id": str(idx),
                                "method": req["method"],
                                "url": req["url"],
                                "headers": req["headers"]
                            }
                            if "body" in req:
                                batch_req["body"] = req["body"]
                            batch_requests.append(batch_req)
                            
                        batch_body = {"requests": batch_requests}
                        batch_headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"
                        }
                        
                        try:
                            # 429 Retry loop for the $batch request
                            for attempt in range(3):
                                async with self._session.post(
                                    "https://graph.microsoft.com/v1.0/$batch",
                                    headers=batch_headers, json=batch_body
                                ) as resp:
                                    if resp.status == 429:
                                        retry_after = int(resp.headers.get("Retry-After", 1))
                                        logger.warning(f"Graph $batch rate limited. Worker sleeping for {retry_after}s...")
                                        await asyncio.sleep(retry_after)
                                        continue
                                        
                                    resp.raise_for_status()
                                    data = await resp.json()
                                    break
                            else:
                                raise Exception("Exceeded max retries for 429 on $batch request")

                            # Map responses back to futures
                            response_map = {r["id"]: r for r in data.get("responses", [])}
                            for idx, req in enumerate(chunk):
                                resp_data = response_map.get(str(idx))
                                if resp_data:
                                    # If an individual item in the batch got a 429, we should technically retry it, 
                                    # but the Graph API usually rate limits at the batch level. 
                                    if resp_data.get("status") == 429:
                                        logger.warning(f"Individual request {idx} in batch hit 429.")
                                        
                                    if not req["future"].done():
                                        req["future"].set_result(resp_data)
                                else:
                                    if not req["future"].done():
                                        req["future"].set_exception(Exception("No response in batch"))
                        except Exception as e:
                            logger.error(f"Error processing Graph batch: {e}")
                            for req in chunk:
                                if not req["future"].done():
                                    req["future"].set_exception(e)
                                    
                # Global throttle: max 1 batch request loop per 1s
                await asyncio.sleep(1)
        finally:
            if self._session:
                await self._session.close()
                self._session = None

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
            'scope': 'offline_access user.read mail.readwrite mail.send calendars.readwrite MailboxSettings.ReadWrite',
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

    async def get_frequent_senders(self, days_back: int = 30, max_senders: int = 15,max_messages: int = 3000, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetches a summary of the most frequent email senders over the specified time period.
        It pulls only the 'from' metadata from recent emails to quickly aggregate counts.
        """
        if not self.access_token:
            raise Exception("Not authenticated")

        since = datetime.utcnow() - timedelta(days=days_back)
        since_str = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        
        # We only need the 'from' field to aggregate counts. Requesting up to 500 max per page to get a good sample size.
        params = {
            "$filter": f"receivedDateTime ge {since_str}",
            "$select": "from",
            "$top": "500",
            "$orderby": "receivedDateTime desc"
        }
        
        sender_counts = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.graph_endpoint}/me/mailFolders/{folder_id}/messages" if folder_id else f"{self.graph_endpoint}/me/messages"
                
                # We'll follow pagination up to a reasonable limit to build the frequency map
                messages_processed = 0
                max_messages_to_process = max_messages
                
                while url and messages_processed < max_messages_to_process:
                    for attempt in range(3):
                        async with session.get(url, headers=headers, params=params) as response:
                            if response.status == 429:
                                retry_after = int(response.headers.get("Retry-After", 1))
                                logger.warning(f"Rate limited fetching frequent senders. Retrying after {retry_after}s...")
                                await asyncio.sleep(retry_after)
                                continue
                            response.raise_for_status()
                            data = await response.json()
                            break
                    else:
                        raise Exception("Exceeded max retries for 429 Too Many Requests")
                        
                    messages = data.get('value', [])
                    for msg in messages:
                        from_data = msg.get("from", {}).get("emailAddress", {})
                        email = from_data.get("address")
                        name = from_data.get("name")
                        if email:
                            if email not in sender_counts:
                                sender_counts[email] = {"name": name, "email": email, "count": 0}
                            sender_counts[email]["count"] += 1
                    messages_processed += len(messages)
                    url = data.get('@odata.nextLink')
                    params = None  # ← nextLink already contains all query params
                    
            # Sort by count descending and return the top N
            sorted_senders = sorted(sender_counts.values(), key=lambda x: x["count"], reverse=True)
            return sorted_senders[:max_senders]
            
        except Exception as e:
            logger.error(f"Error aggregating frequent senders: {e}", exc_info=True)
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

    async def get_emails_from_sender(self, sender_email: str, max_results: int = 10, folder_id: Optional[str] = None) -> List[Dict]:
        """Fetches the most recent emails from a specific sender."""
        if not self.access_token:
            raise Exception("Not authenticated")
        
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        
        # Cap page size to 500 for Graph API limits, but we can fetch multiple pages
        page_size = min(max_results, 500)
        
        params = {
            "$search": f'"from:{sender_email}"',
            "$select": "id,subject,from,receivedDateTime,bodyPreview",
            "$top": str(page_size),
        }
        
        all_formatted_messages = []
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.graph_endpoint}/me/mailFolders/{folder_id}/messages" if folder_id else f"{self.graph_endpoint}/me/messages"
                
                while url and len(all_formatted_messages) < max_results:
                    for attempt in range(3):
                        async with session.get(url, headers=headers, params=params) as response:
                            if response.status == 429:
                                retry_after = int(response.headers.get("Retry-After", 1))
                                logger.warning(f"Rate limited fetching emails from {sender_email}. Retrying after {retry_after}s...")
                                await asyncio.sleep(retry_after)
                                continue
                            response.raise_for_status()
                            data = await response.json()
                            break
                    else:
                        raise Exception("Exceeded max retries for 429 Too Many Requests")
                        
                    messages = data.get('value', [])
                    if not messages:
                        break
                        
                    for msg in messages:
                        def _clean_snippet(snippet: str) -> str:
                            if not snippet:
                                return ""
                            import re
                            cleaned = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]', '', snippet)
                            cleaned = re.sub(r'[\xa0\u2007\u202f]', ' ', cleaned)
                            return re.sub(r'\s+', ' ', cleaned).strip()

                        all_formatted_messages.append({
                            "id": msg.get("id"),
                            "subject": msg.get("subject", "No Subject"),
                            "from": msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown"),
                            "receivedDateTime": msg.get("receivedDateTime"),
                            "snippet": _clean_snippet(msg.get("bodyPreview", ""))
                        })
                        if len(all_formatted_messages) >= max_results:
                            break
                            
                    # Clear params for next page because the nextLink already contains the $top and $search logic
                    params = None 
                    url = data.get('@odata.nextLink')
                    
            return all_formatted_messages
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

    async def mark_email_read(self, message_id: str, is_read: bool = True) -> bool:
        """Marks a specific email as read or unread."""
        if not self.access_token:
            raise Exception("Not authenticated")

        queue = GraphBatchQueue()
        payload = {"isRead": is_read}
        
        for attempt in range(3):
            try:
                resp = await queue.enqueue_request(
                    access_token=self.access_token,
                    method="PATCH",
                    url=f"/me/messages/{message_id}",
                    body=payload
                )
                inner_status = resp.get("status", 500)
                if inner_status == 429:
                    headers = resp.get("headers", {})
                    retry_after = int(headers.get("Retry-After", 2))
                    logger.warning(f"Batch item {message_id} rate limited (429). Retrying after {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                if not (200 <= inner_status < 300):
                    raise Exception(f"Failed to mark read: {inner_status}")
                return True
            except Exception as e:
                if attempt == 2:
                    logger.error(f"Error marking email {message_id} as read={is_read}: {e}", exc_info=True)
                    raise
                await asyncio.sleep(1)

    async def categorize_email(self, message_id: str, categories: List[str]) -> bool:
        """Adds or removes categories from a specific email."""
        if not self.access_token:
            raise Exception("Not authenticated")

        queue = GraphBatchQueue()
        payload = {"categories": categories}
        
        for attempt in range(3):
            try:
                resp = await queue.enqueue_request(
                    access_token=self.access_token,
                    method="PATCH",
                    url=f"/me/messages/{message_id}",
                    body=payload
                )
                inner_status = resp.get("status", 500)
                if inner_status == 429:
                    headers = resp.get("headers", {})
                    retry_after = int(headers.get("Retry-After", 2))
                    logger.warning(f"Batch item {message_id} rate limited (429). Retrying after {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                if not (200 <= inner_status < 300):
                    raise Exception(f"Failed to categorize: {inner_status}")
                return True
            except Exception as e:
                if attempt == 2:
                    logger.error(f"Error categorizing email {message_id}: {e}", exc_info=True)
                    raise
                await asyncio.sleep(1)

    async def move_email(self, message_id: str, destination_folder_id: str) -> bool:
        """Moves an email to a different folder."""
        if not self.access_token:
            raise Exception("Not authenticated")

        queue = GraphBatchQueue()
        payload = {"destinationId": destination_folder_id}
        
        for attempt in range(3):
            try:
                resp = await queue.enqueue_request(
                    access_token=self.access_token,
                    method="POST",
                    url=f"/me/messages/{message_id}/move",
                    body=payload
                )
                inner_status = resp.get("status", 500)
                if inner_status == 429:
                    headers = resp.get("headers", {})
                    retry_after = int(headers.get("Retry-After", 2))
                    logger.warning(f"Batch item {message_id} rate limited (429). Retrying after {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                if not (200 <= inner_status < 300):
                    raise Exception(f"Failed to move: {inner_status}")
                return True
            except Exception as e:
                if attempt == 2:
                    logger.error(f"Error moving email {message_id} to folder {destination_folder_id}: {e}", exc_info=True)
                    raise
                await asyncio.sleep(1)

    async def search_emails(self, query: str, max_results: int = 10) -> List[Dict]:
        """Searches the user's emails using a specific query string."""
        if not self.access_token:
            raise Exception("Not authenticated")

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        params = {
            "$search": f'"{query}"',
            "$select": "id,subject,from,receivedDateTime,bodyPreview",
            "$top": str(max_results)
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.graph_endpoint}/me/messages"
                for attempt in range(3):
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 429:
                            retry_after = int(response.headers.get("Retry-After", 1))
                            logger.warning(f"Rate limited searching emails. Retrying after {retry_after}s...")
                            await asyncio.sleep(retry_after)
                            continue
                        response.raise_for_status()
                        data = await response.json()
                        break
                else:
                    raise Exception("Exceeded max retries for 429 Too Many Requests")
                    
            messages = data.get('value', [])
            
            def _clean_snippet(snippet: str) -> str:
                if not snippet:
                    return ""
                # Replace unicode zero-width spaces, non-breaking spaces, and normalize whitespace
                import re
                cleaned = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]', '', snippet)
                cleaned = re.sub(r'[\xa0\u2007\u202f]', ' ', cleaned)
                return re.sub(r'\s+', ' ', cleaned).strip()

            return [{
                "id": msg.get("id"),
                "subject": msg.get("subject", "No Subject"),
                "from": msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown"),
                "receivedDateTime": msg.get("receivedDateTime"),
                "snippet": _clean_snippet(msg.get("bodyPreview", ""))
            } for msg in messages]
        except Exception as e:
            logger.error(f"Error searching emails for query '{query}': {e}", exc_info=True)
            return []

    async def list_mail_folders(self) -> List[Dict]:
        """Lists all the mail folders in the user's mailbox (including custom ones)."""
        if not self.access_token:
            raise Exception("Not authenticated")

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.graph_endpoint}/me/mailFolders", headers=headers) as response:
                    response.raise_for_status()
                    data = await response.json()
            return [{"id": f["id"], "name": f["displayName"]} for f in data.get('value', [])]
        except Exception as e:
            logger.error(f"Error fetching mail folders: {e}", exc_info=True)
            return []

    async def create_mail_folder(self, display_name: str) -> Dict[str, Any]:
        """Creates a new mail folder in the user's mailbox."""
        if not self.access_token:
            raise Exception("Not authenticated")

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {"displayName": display_name, "isHidden": False}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.graph_endpoint}/me/mailFolders", headers=headers, json=payload) as response:
                    response.raise_for_status()
                    data = await response.json()
            return {"id": data.get("id"), "name": data.get("displayName")}
        except Exception as e:
            logger.error(f"Error creating mail folder '{display_name}': {e}", exc_info=True)
            raise

    async def create_outlook_rule(self, display_name: str, sequence: int, sender_contains: str, move_to_folder_id: str) -> Dict[str, Any]:
        """Creates an Outlook rule to automatically move messages from a specific sender to a folder."""
        if not self.access_token:
            raise Exception("Not authenticated")

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {
            "displayName": display_name,
            "sequence": sequence,
            "isEnabled": True,
            "conditions": {
                "senderContains": [sender_contains]
            },
            "actions": {
                "moveToFolder": move_to_folder_id,
                "stopProcessingRules": True
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                for attempt in range(3):
                    async with session.post(f"{self.graph_endpoint}/me/mailFolders/inbox/messageRules", headers=headers, json=payload) as response:
                        if response.status == 429:
                            retry_after = int(response.headers.get("Retry-After", 1))
                            logger.warning(f"Rate limited creating rule '{display_name}'. Retrying after {retry_after}s...")
                            await asyncio.sleep(retry_after)
                            continue
                        response.raise_for_status()
                        return await response.json()
                raise Exception("Exceeded max retries for 429 Too Many Requests")
        except Exception as e:
            logger.error(f"Error creating Outlook rule '{display_name}': {e}", exc_info=True)
            raise

    async def bulk_categorize_emails(self, message_ids: List[str], categories: List[str]) -> Dict[str, Any]:
        """Adds or removes categories from multiple emails simultaneously using the global GraphBatchQueue."""
        if not self.access_token:
            raise Exception("Not authenticated")

        queue = GraphBatchQueue()
        payload = {"categories": categories}
        
        async def _categorize(msg_id):
            for attempt in range(3):
                try:
                    resp = await queue.enqueue_request(
                        access_token=self.access_token,
                        method="PATCH",
                        url=f"/me/messages/{msg_id}",
                        body=payload
                    )
                    inner_status = resp.get("status", 500)
                    
                    if inner_status == 429:
                        headers = resp.get("headers", {})
                        retry_after = int(headers.get("Retry-After", 2))
                        logger.warning(f"Batch item {msg_id} rate limited (429). Retrying after {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue
                        
                    status = "success" if 200 <= inner_status < 300 else "failed"
                    return {"id": msg_id, "status": status, "error_code": inner_status if status == "failed" else None}
                except Exception as ex:
                    if attempt == 2:
                        return {"id": msg_id, "status": "failed", "error": str(ex)}
                    await asyncio.sleep(1)
            return {"id": msg_id, "status": "failed", "error": "Exceeded max retries for item"}

        tasks = [_categorize(msg_id) for msg_id in message_ids]
        results = await asyncio.gather(*tasks)
            
        success_count = sum(1 for r in results if r["status"] == "success")
        return {"processed": len(message_ids), "successes": success_count, "failures": len(message_ids) - success_count, "results": results}

    async def bulk_move_emails(self, message_ids: List[str], destination_folder_id: str) -> Dict[str, Any]:
        """Moves multiple emails simultaneously using the global GraphBatchQueue to avoid rate limits."""
        if not self.access_token:
            raise Exception("Not authenticated")
        
        queue = GraphBatchQueue()
        payload = {"destinationId": destination_folder_id}
        
        async def _move(msg_id):
            for attempt in range(3):
                try:
                    resp = await queue.enqueue_request(
                        access_token=self.access_token,
                        method="POST",
                        url=f"/me/messages/{msg_id}/move",
                        body=payload
                    )
                    # The batch response inner status is an int
                    inner_status = resp.get("status", 500)
                    
                    if inner_status == 429:
                        # Grab Retry-After if provided in the body headers, else default to 2s backoff
                        headers = resp.get("headers", {})
                        retry_after = int(headers.get("Retry-After", 2))
                        logger.warning(f"Batch item {msg_id} rate limited (429). Retrying after {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue
                        
                    status = "success" if 200 <= inner_status < 300 else "failed"
                    return {"id": msg_id, "status": status, "error_code": inner_status if status == "failed" else None}
                except Exception as ex:
                    if attempt == 2:
                        return {"id": msg_id, "status": "failed", "error": str(ex)}
                    await asyncio.sleep(1)
            return {"id": msg_id, "status": "failed", "error": "Exceeded max retries for item"}

        tasks = [_move(msg_id) for msg_id in message_ids]
        results = await asyncio.gather(*tasks)
        
        success_count = sum(1 for r in results if r["status"] == "success")
        return {"processed": len(message_ids), "successes": success_count, "failures": len(message_ids) - success_count, "results": results}
    async def _graph_get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            **PREFER_IMMUTABLE_ID,
        }
        logger.info(f'requesting from {url}')
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers, params=params)
            try:
                r.raise_for_status()
                logger.info('req success')
            except httpx.HTTPStatusError as e:
                detail = ""
                try:
                    detail = f" ; graph_error={r.json()}"
                except Exception:
                    detail = f" ; body={r.text[:500]}"
                raise httpx.HTTPStatusError(f"{e}{detail}", request=e.request, response=e.response) from None
            return r.json()

    async def get_message_with_attachments(
        self, *, ms_user_id: str, message_id: str
    ) -> Dict[str, Any]:
        """
        Robust: /me + RAW immutable id + no $expand.
        Then page attachments from child collection (ask for @odata.type + contentBytes).
        """
        base = f"{self.graph_endpoint}/me/messages/{message_id}"
        select_fields = (
            "id,subject,body,from,toRecipients,receivedDateTime,conversationId,webLink,internetMessageHeaders"
        )
        
        # 1) Get message (no expand)
        msg = await self._graph_get(base, {"$select": select_fields})
        try:
            logger.info('msg obtained')
            # 2) Get attachments (child collection), try to include contentBytes directly
            # Also request @odata.type so we can branch on fileAttachment vs itemAttachment if needed
            attachments = await self._graph_get(f"{base}/attachments", {"$top": 50})
            # print('atts', json.dumps(attachments,indent=4))
            # 2) Helpers
            file_attachments = []
            item_attachments = []
            ref_attachments = []
            for att in attachments.get("value", []):
                att_type = att.get("@odata.type", "").lower()
                if att_type == "#microsoft.graph.fileattachment":
                    att['attachmentType'] = 'file'
                    file_attachments.append(att)
                elif att_type == "#microsoft.graph.itemattachment":
                    att['attachmentType'] = 'item'
                    item_attachments.append(att)
                elif att_type == "#microsoft.graph.referenceattachment":
                    att['attachmentType'] = 'reference'
                    ref_attachments.append(att)
                else:
                    logger.warning(f"Unknown attachment type: {att_type}")


            attachments = file_attachments + item_attachments + ref_attachments
            # Optional enrichment: some fileAttachments may still lack contentBytes
            enriched: list[dict] = []
            for a in attachments:
                # You can still check the metadata key (present even if not selected)
                otype = (a.get("@odata.type") or "").lower()
                if "fileattachment" in otype and "contentBytes" not in a:
                    try:
                        att = await self._graph_get(
                            f"{base}/attachments/{a['id']}",
                            {"$select": "id,name,contentType,size,isInline,contentBytes"},
                        )
                        a = {**a, **att}
                    except Exception:
                        # fallback to $value later if you truly need the bytes
                        pass
                enriched.append(a)

            msg["attachments"] = enriched 
        except Exception as e:
            logger.error(f"Error fetching attachments for message {message_id}: {e}", exc_info=True)
            msg["attachments"] = []
        return msg

    async def _translate_to_rest_id(self, raw_id: str) -> Optional[str]:
        """
        Translate an Exchange immutable id (AAMk...=) to a REST id.
        Returns the translated id or None on failure.
        """
        url = f"{self.graph_endpoint}/me/translateExchangeIds"
        payload = {
            "inputIds": [raw_id],
            "sourceIdType": "immutableId",
            "targetIdType": "restId"
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # no IdType header here; this endpoint expects the payload
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers=headers, json=payload)
            try:
                r.raise_for_status()
                data = r.json()
                out = (data.get("value") or [{}])[0]
                return out.get("targetId")
            except Exception as e:
                logger.warning(f"Failed translating id via translateExchangeIds: {e}")
                return None
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
            if a.get("@odata.type", "").endswith("fileAttachment") and a.get("contentBytes"):
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
            "from": (msg.get("from") or {}),
            "to": msg.get("toRecipients",[]),
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
    Returns (ms_user_id, message_id) given a resource path.
    This version is case-insensitive.
    """
    if not resource:
        return None, None

    # Try matching the simpler path first
    # Note the re.IGNORECASE flag
    m = re.search(r"Users/([^/]+)/messages/([^/?]+)", resource, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)

    # Then try the more complex mailFolders path
    m2 = re.search(r"Users/([^/]+)/mailFolders\('[^']+'\)/messages/([^/?]+)", resource, re.IGNORECASE)
    if m2:
        return m2.group(1), m2.group(2)

    return None, None