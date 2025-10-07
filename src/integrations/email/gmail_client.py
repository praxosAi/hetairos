import asyncio
import base64
import mimetypes
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional,Tuple
from email.message import EmailMessage
from src.utils.blob_utils import upload_to_blob_storage,upload_bytes_to_blob_storage
from src.utils.logging.base_logger import setup_logger
from src.utils.rate_limiter import rate_limiter
from src.utils.circuit_breaker import gmail_auth_breaker, gmail_api_breaker
from praxos_python.types.message import Message
from src.integrations.base_integration import BaseIntegration
from src.utils.database import db_manager
from src.config.settings import settings
from src.services.integration_service import integration_service
from bson import ObjectId
import quopri
from html import unescape
import re

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
        integration_record = await integration_service.get_integration_record_for_user_and_name(self.user_id, 'gmail')
        if integration_record:
            self.gmail_address = integration_record.get('connected_account')
            
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

    async def search_emails(self, query: str, max_results: int = 10) -> List[Dict]:
        """Searches for emails using a generic query string."""
        if not self.service:
            raise Exception("Gmail service not initialized. Call authenticate() first.")

        results = self.service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return []

        email_list = []
        for msg in messages:
            try:
                msg_data = self.service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
                headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
                email_list.append({
                    "id": msg_data['id'],
                    "subject": headers.get('Subject', 'No Subject'),
                    "snippet": msg_data.get('snippet', '')
                })
            except HttpError as e:
                logger.error(f"Error fetching metadata for message {msg['id']}: {e}")
                continue
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

    def get_changed_message_ids_since(
        self,
        start_history_id: str,
        user_id: str = "me",
        history_types: Optional[List[str]] = None,
    ) -> Tuple[List[str], Optional[str]]:
        history_types = history_types or ["messageAdded"]
        msg_ids: List[str] = []
        page_token = None
        max_history_id_seen: Optional[int] = None
        try:
            while True:
                req = self.service.users().history().list(
                    userId=user_id,
                    startHistoryId=str(start_history_id),
                    pageToken=page_token,
                    historyTypes=history_types,
                    # labelId=["INBOX"],  # only if your watch was scoped to INBOX
                )
                resp = req.execute()

                for h in resp.get("history", []):
                    hid = int(h["id"])
                    if max_history_id_seen is None or hid > max_history_id_seen:
                        max_history_id_seen = hid
                    for item in h.get("messagesAdded", []):
                        msg_ids.append(item["message"]["id"])

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception as e:
            logger.error(f"Error fetching Gmail history for user {self.user_id}: {e}")
            return msg_ids, None

        # de-dupe, preserve order
        seen, deduped = set(), []
        for mid in msg_ids:
            if mid not in seen:
                seen.add(mid)
                deduped.append(mid)

        new_checkpoint = str(max_history_id_seen) if max_history_id_seen is not None else None
        return deduped, new_checkpoint

    # def get_changed_message_ids_since(
    #     self,
    #     start_history_id: str,
    #     user_id: str = "me",
    #     history_types: Optional[List[str]] = ["messageAdded"],
    # ) -> Tuple[List[str], Optional[str]]:
    #     """
    #     Returns (message_ids, new_checkpoint_history_id).
    #     `new_checkpoint_history_id` should be saved and used as the next startHistoryId.
    #     """
    #     history_types = history_types or ["messageAdded"]  # common case
    #     msg_ids: List[str] = []
    #     page_token = None
    #     max_history_id_seen: Optional[int] = None
    #     try:
    #         while True:
    #             req = self.service.users().history().list(
    #                 userId=user_id,
    #                 startHistoryId=str(start_history_id),
    #                 pageToken=page_token,
    #                 historyTypes=history_types,
    #             )
    #             resp = req.execute()

    #             for h in resp.get("history", []):
    #                 # Track the largest history id we see
    #                 hid = int(h.get("id"))
    #                 if max_history_id_seen is None or hid > max_history_id_seen:
    #                     max_history_id_seen = hid

    #                 # Collect messages from messagesAdded; you can also look at messagesDeleted, labelsAdded, etc.
    #                 for item in h.get("messagesAdded", []):
    #                     mid = item["message"]["id"]
    #                     msg_ids.append(mid)

    #             page_token = resp.get("nextPageToken")
    #             if not page_token:
    #                 break
    #     except Exception as e:
    #         logger.error(f"Error fetching Gmail history for user {self.user_id}: {e}")
    #         # If we get an error, we return the messages we've collected so far,
    #         # but we don't update the checkpoint, so we'll retry from the same place next time.
    #         return msg_ids, None
    #     # Use the largest history id we processed as the new checkpoint
    #     new_checkpoint = str(max_history_id_seen) if max_history_id_seen is not None else None
    #     return msg_ids, new_checkpoint
    
    def get_messages_by_ids(self, message_ids: List[str], user_id: str = "me") -> List[Dict[str, Any]]:
        out = []
        for mid in message_ids:
            msg = self.service.users().messages().get(userId=user_id, id=mid, format="full").execute()
            out.append(msg)
        return out

    def _headers_to_map(self, headers: List[Dict[str, str]]) -> Dict[str, str]:
        return {h["name"]: h["value"] for h in headers or []}

    def _decode_b64url_bytes(self, data: str) -> bytes:
        return base64.urlsafe_b64decode(data.encode("utf-8"))

    def _maybe_qp_decode(self, raw: bytes, cte: str) -> bytes:
        if (cte or "").lower() == "quoted-printable":
            return quopri.decodestring(raw)
        return raw

    def _bytes_to_text(self, raw: bytes, charset: Optional[str]) -> str:
        enc = (charset or "utf-8").lower()
        try:
            return raw.decode(enc, errors="replace")
        except Exception:
            return raw.decode("utf-8", errors="replace")

    def _walk_parts_collect_bodies(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Returns (plain_text, html_text)
        """
        plain, html = None, None

        def _walk(p: Dict[str, Any]):
            nonlocal plain, html
            mt = (p.get("mimeType") or "").lower()
            body = p.get("body") or {}
            data = body.get("data")
            headers = {h["name"].lower(): h["value"] for h in p.get("headers", [])}
            cte = headers.get("content-transfer-encoding", "")
            # e.g. 'text/plain; charset="UTF-8"'
            ct = headers.get("content-type", "")
            charset = None
            if "charset=" in ct:
                charset = ct.split("charset=", 1)[1].strip().strip('"').strip("'").split(";")[0]

            if data:
                raw = self._decode_b64url_bytes(data)
                raw = self._maybe_qp_decode(raw, cte)
                text = self._bytes_to_text(raw, charset)

                if mt.startswith("text/plain") and plain is None:
                    plain = text
                elif mt.startswith("text/html") and html is None:
                    html = text

            for child in p.get("parts") or []:
                if plain is not None and html is not None:
                    break
                _walk(child)

        _walk(payload or {})
        return plain, html

    async def _extract_body(self, payload: Dict) -> str:
        plain, html = self._walk_parts_collect_bodies(payload)
        # Prefer plain text; fallback to html if needed.
        return plain or html or ""

    async def _download_and_store_attachment(
        self,
        *,
        user_record: Dict[str, Any],
        message_id: str,
        part: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Downloads a single Gmail attachment part to blob storage, inserts a 'documents' row,
        and returns a normalized file dict for event payload.
        """
        body = part.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            return {}

        # 1) fetch attachment bytes
        att = self.service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        data_b64 = att.get("data")
        if not data_b64:
            return {}

        raw_bytes = base64.urlsafe_b64decode(data_b64.encode("utf-8"))
        filename = part.get("filename") or "attachment"
        mime_type = part.get("mimeType") or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # 2) upload to blob
        blob_name = f"{str(user_record['_id'])}/gmail/{message_id}/{filename}"
        blob_path = await upload_bytes_to_blob_storage(raw_bytes, blob_name, content_type=mime_type)

        # 3) insert documents row (idempotency via your upstream unique platform_message_id for the email)
        document_entry = {
            "user_id": ObjectId(user_record["_id"]),
            "platform": "gmail",
            "platform_file_id": attachment_id,
            "platform_message_id": message_id,
            "type": "document",
            "blob_path": blob_name,
            "mime_type": mime_type,
            "file_name": filename,
        }
        inserted_id = await db_manager.add_document(document_entry)

        # 4) normalized file record for payload
        return {
            "type": "document",
            "blob_path": blob_path,
            "mime_type": mime_type,
            "caption": "",
            "file_name": filename,
            "inserted_id": str(inserted_id),
        }

    async def _collect_attachments_normalized(
        self,
        *,
        user_record: Dict[str, Any],
        message: Dict[str, Any],
    ) -> List[Dict[str, Any]]:      
        """
        Walks all parts and downloads any with a filename (true attachment). Inline images will also be included if they have filename + attachmentId.
        """
        results: List[Dict[str, Any]] = []

        def _parts(p: Dict[str, Any]):
            yield p
            for c in p.get("parts", []) or []:
                yield from _parts(c)

        for p in _parts(message.get("payload") or {}):
            filename = p.get("filename") or ""
            body = p.get("body", {}) or {}
            if filename and body.get("attachmentId"):
                file_rec = await self._download_and_store_attachment(
                    user_record=user_record,
                    message_id=message["id"],
                    part=p,
                )
                if file_rec:
                    results.append(file_rec)
        return results
    
    def _strip_html(self, html: str) -> str:
        # very light strip; good enough for notifications
        text = re.sub(r"<(script|style)\b[^<]*(?:(?!</\1>)<[^<]*)*</\1>", "", html, flags=re.I)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return unescape(text).strip()
    async def normalize_gmail_message_for_ingestion(
        self,
        *,
        user_record: Dict[str, Any],
        message: Dict[str, Any],
        command_prefix: str = "",
    ) -> Dict[str, Any]:
        """
        Returns a dict shaped like your other webhooks:
        payload.text, payload.files[], metadata, etc.
        """
        headers = self._headers_to_map(message.get("payload", {}).get("headers", []))
        plain, html = self._walk_parts_collect_bodies(message.get("payload", {}) or {})
        body_text = plain or (self._strip_html(html) if html else "")
        if command_prefix:
            body_text = f"{command_prefix}\n\n{body_text}" if body_text else command_prefix

        files = await self._collect_attachments_normalized(
            user_record=user_record,
            message=message,
        )

        normalized = {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "subject": headers.get("Subject", "No Subject"),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "timestamp": message.get("internalDate"),
            "labels": message.get("labelIds", []),
            "snippet": message.get("snippet", ""),
            "payload": {
                "text": body_text,
                "files": files if files else [],
            },
            "metadata": {
                "platform": "gmail",
                "gmail_message_id": message.get("id"),
                "gmail_thread_id": message.get("threadId"),
                # "headers": headers,
                "history_id": message.get("historyId"),  # may be absent on single GET
            },
        }
        return normalized