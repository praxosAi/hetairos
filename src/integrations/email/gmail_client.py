import asyncio
import base64
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from email.message import EmailMessage
from src.utils.logging.base_logger import setup_logger
from src.utils.rate_limiter import rate_limiter
from src.utils.circuit_breaker import gmail_auth_breaker, gmail_api_breaker
from praxos_python.types.message import Message
from src.integrations.base_integration import BaseIntegration
from src.config.settings import settings
from src.services.integration_service import integration_service

logger = setup_logger(__name__)

class GmailIntegration(BaseIntegration):
    
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.service = None
        self.people_service = None
        self.credentials = None
        self.gmail_user_id = 'me'
        self.gmail_address = None
    
    async def authenticate(self) -> bool:
        """Authenticate with Gmail API with circuit breaker protection"""
        try:
            return await gmail_auth_breaker.call(self._authenticate_internal)
        except Exception as e:
            logger.error(f"Gmail authentication failed: {e}")
            return False
    
    async def _authenticate_internal(self) -> bool:
        """Internal authentication method"""
        if not all([settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET]):
            logger.error("Gmail credentials not configured")
            return False
        
        logger.info(f"Creating Google credentials for user {self.user_id}")
        self.credentials = await integration_service.create_google_credentials(self.user_id, 'gmail')

        if not self.credentials:
            logger.error("Failed to create Google credentials")
            return False
        logger.info(f"obtained google credentials for user {self.user_id}")
        # Build Gmail service
        self.service = build('gmail', 'v1', credentials=self.credentials)
        self.people_service = build('people', 'v1', credentials=self.credentials)
        logger.info(f"built gmail and people services for user {self.user_id}")
        return True
    
    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent emails since last sync"""
        if not self.service:
            return []
        
        try:
            # Check rate limits
            is_allowed, remaining = rate_limiter.check_limit(self.user_id, "emails")
            if not is_allowed:
                logger.error(f"Email rate limit exceeded for user {self.user_id}")
                return []
            
            # Default to emails from 7 days ago if no since timestamp
            if since is None:
                since = datetime.utcnow() - timedelta(days=7)
            
            # Convert datetime to Gmail query format
            since_str = since.strftime('%Y/%m/%d')
            query = f'after:{since_str}'
            
            # List messages
            result = self.service.users().messages().list(
                userId=self.gmail_user_id,
                q=query,
                maxResults=min(settings.MAX_EMAILS, remaining)  # Respect rate limits
            ).execute()
            
            messages = result.get('messages', [])
            
            # Fetch detailed information for each message
            detailed_messages = []
            processed_count = 0
            attachment_count = 0
            
            for message in messages:
                if processed_count >= settings.MAX_EMAILS:
                    break
                
                # Check if we can process more attachments
                if attachment_count >= settings.MAX_EMAIL_ATTACHMENTS:
                    # Skip messages with attachments if we've hit the limit
                    continue
                
                try:
                    msg_detail = self.service.users().messages().get(
                        userId=self.gmail_user_id,
                        id=message['id'],
                        format='full'
                    ).execute()
                    
                    formatted_message = await self._format_message(msg_detail)
                    
                    # Count attachments
                    message_attachment_count = len(formatted_message.get('attachments', []))
                    if attachment_count + message_attachment_count <= settings.MAX_EMAIL_ATTACHMENTS:
                        detailed_messages.append(formatted_message)
                        attachment_count += message_attachment_count
                        processed_count += 1
                        
                        # Update rate limiter
                        rate_limiter.increment_usage(self.user_id, "emails", 1)
                        if message_attachment_count > 0:
                            rate_limiter.increment_usage(self.user_id, "email_attachments", message_attachment_count)
                    
                except HttpError as e:
                    logger.error(f"Error fetching message {message['id']}: {e}")
                    continue
            
            return detailed_messages
            
        except Exception as e:
            logger.error(f"Error fetching Gmail messages: {e}")
            return []

    async def _format_message(self, message: Dict) -> Dict:
        """Format Gmail message into standardized format"""
        headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
        
        formatted_message = {
            "id": message['id'],
            "thread_id": message.get('threadId'),
            "subject": headers.get('Subject', 'No Subject'),
            "from": headers.get('From', ''),
            "to": headers.get('To', ''),
            "date": headers.get('Date', ''),
            "timestamp": message.get('internalDate'),
            "snippet": message.get('snippet', ''),
            "body": await self._extract_body(message['payload']),
            "attachments": await self._extract_attachments(message),
            "source": "gmail",
            "labels": message.get('labelIds', [])
        }
        
        return formatted_message
    
    async def _extract_body(self, payload: Dict) -> str:
        """Extract email body from message payload"""
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
                elif part['mimeType'] == 'text/html' and not body:
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        elif 'data' in payload['body']:
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        return body

    async def _extract_attachments(self, message: Dict) -> List[Dict]:
        """Extract attachment information from message"""
        attachments = []
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part.get('filename'):
                    attachments.append({
                        "id": part['body'].get('attachmentId'),
                        "filename": part['filename'],
                        "mimetype": part['mimeType'],
                        "size": part['body'].get('size', 0),
                        "message_id": message['id']
                    })
        return attachments

    async def send_email(self, recipient: str, subject: str, body: str) -> Dict:
        """Sends an email using Gmail API."""
        if not self.service:
            raise Exception("Gmail service not initialized. Call authenticate() first.")
        
        message = EmailMessage()
        # Check if body contains HTML tags, if so send as HTML
        if '<' in body and '>' in body:
            # Convert newlines to HTML line breaks for HTML emails
            html_body = body.replace('\n', '<br>')
            message.add_alternative(html_body, subtype='html')
        else:
            message.set_content(body)
        message['To'] = recipient
        message['Subject'] = subject
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message_request = {'raw': encoded_message}
        
        sent_message = self.service.users().messages().send(
            userId='me',
            body=create_message_request
        ).execute()
        
        return {"email_id": sent_message['id']}

    async def get_emails_from_sender(self, sender_email: str, max_results: int = 10) -> List[Dict]:
        """Fetches the most recent emails from a specific sender."""
        if not self.service:
            raise Exception("Gmail service not initialized. Call authenticate() first.")

        query = f"from:{sender_email}"
        results = self.service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return []

        email_list = []
        for msg in messages:
            msg_data = self.service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
            email_list.append({
                "subject": headers.get('Subject', 'No Subject'),
                "snippet": msg_data.get('snippet', '')
            })
        return email_list

    def get_user_email_address(self) -> str:
        """Gets the authenticated user's Gmail email address."""
        if self.gmail_address:
            return self.gmail_address

        if not self.service:
            raise Exception("Gmail service not initialized. Call authenticate() first.")
        
        try:
            profile = self.service.users().getProfile(userId=self.gmail_user_id).execute()
            self.gmail_address = profile.get('emailAddress', '')
            return self.gmail_address
        except Exception as e:
            logger.error(f"Error fetching user email address: {e}")
            raise Exception(f"Failed to get user email address: {e}")

    async def find_contact_email(self, name: str) -> List[Dict]:
        """Searches the user's Google Contacts for a person's email address by their name."""
        if not self.people_service:
            logger.error("Google People API service not initialized. Call authenticate() first.")
            raise Exception("Google People API service not initialized. Call authenticate() first.")
        logger.info(f"searching for contact {name} for user {self.user_id}")
        results = self.people_service.people().searchContacts(
            query=name,
            readMask="names,emailAddresses,nicknames"
        ).execute()
        logger.info(f"search results for contact {name} for user {self.user_id}: {results}")
        contacts = results.get('results', [])
        if not contacts:
            ### if no contacts found, we should search for other contacts.
            results = self.people_service.otherContacts().search(
            query=f"{name}*",
            readMask="names,emailAddresses,nicknames"
            ).execute()
            logger.info(f"search results for other contacts for user {self.user_id}: {results}")
            contacts = results.get('results', [])
            if not contacts:
                logger.info(f"no other contacts found for user {self.user_id}")
                return []
        logger.info(f"contacts found for user {self.user_id}: {contacts}")

        contact_list = []
        for person_result in contacts:
            person = person_result.get('person', {})
            names = person.get('names', [{}])
            emails = person.get('emailAddresses', [{}])
            contact_list.append({
                "name": names[0].get('displayName', 'N/A'),
                "email": emails[0].get('value', 'N/A')
            })
        return contact_list

    # --- Gmail Push Notification Methods ---

    async def setup_push_notifications(self, topic_name: str) -> Optional[Dict]:
        """Sets up Gmail push notifications to a Google Cloud Pub/Sub topic."""
        if not self.service:
            raise Exception("Gmail service not initialized.")
        
        request = {
            'labelIds': ['INBOX'],
            'topicName': topic_name
        }
        try:
            result = self.service.users().watch(userId='me', body=request).execute()
            logger.info(f"Gmail push notifications setup for user {self.user_id}. History ID: {result.get('historyId')}")
            return result
        except Exception as e:
            logger.error(f"Failed to setup Gmail push notifications for user {self.user_id}: {e}")
            return None

    async def stop_push_notifications(self) -> bool:
        """Stops active Gmail push notifications."""
        if not self.service:
            raise Exception("Gmail service not initialized.")
        try:
            self.service.users().stop(userId='me').execute()
            logger.info(f"Gmail push notifications stopped for user {self.user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop Gmail push notifications for user {self.user_id}: {e}")
            return False

    async def get_history_since(self, history_id: str) -> List[Dict]:
        """Fetches email changes since the given historyId."""
        if not self.service:
            return []
        
        try:
            history_result = self.service.users().history().list(
                userId='me',
                startHistoryId=history_id,
                historyTypes=['messageAdded']
            ).execute()
            
            history_items = history_result.get('history', [])
            new_messages = []
            for item in history_items:
                for msg_added in item.get('messagesAdded', []):
                    msg_id = msg_added.get('message', {}).get('id')
                    if msg_id:
                        msg_detail = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                        formatted_message = await self._format_message(msg_detail)
                        new_messages.append(formatted_message)
            
            logger.info(f"Retrieved {len(new_messages)} new messages from history since {history_id}")
            return new_messages
        except Exception as e:
            logger.error(f"Error fetching Gmail history for user {self.user_id}: {e}")
            return []
