import asyncio
import base64
import mimetypes
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional, Tuple
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
from src.services.integration_service import integration_service

logger = setup_logger(__name__)

class GmailIntegration(BaseIntegration):
    

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.services: Dict[str, Any] = {}
        self.people_services: Dict[str, Any] = {}
        self.credentials: Dict[str, Any] = {}
        self.connected_accounts: List[str] = []
        self.gmail_user_id = 'me'

    async def authenticate(self) -> bool:
        """
        Authenticates all connected Gmail accounts for the user and builds
        a service object for each one.
        """
        
        logger.info(f"Authenticating all Gmail accounts for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(self.user_id, 'gmail')

        if not integration_records:
            logger.warning(f"No Gmail integrations found for user {self.user_id}")
            return False

        auth_tasks = []
        for record in integration_records:
            if record:
                auth_tasks.append(self._authenticate_one_account(record))
        
        results = await asyncio.gather(*auth_tasks)
        
        # Returns True if at least one account was successfully authenticated.
        return any(results)

    async def _authenticate_one_account(self, integration_record: str) -> bool:
        account_email = integration_record.get('connected_account')
        integration_id = integration_record.get('_id')
        """Internal method to authenticate a single account and store its services."""
        creds = await integration_service.create_google_credentials(self.user_id, 'gmail', integration_id)
        if not creds:
            logger.error(f"Failed to create credentials for {account_email} for user {self.user_id}")
            return False

        try:
            gmail_service = build('gmail', 'v1', credentials=creds)
            people_service = build('people', 'v1', credentials=creds)

            # Store the authenticated services and details in our dictionaries
            self.services[account_email] = gmail_service
            self.people_services[account_email] = people_service
            self.credentials[account_email] = creds
            if account_email not in self.connected_accounts:
                self.connected_accounts.append(account_email)
            
            logger.info(f"Successfully authenticated and built services for {account_email}")
            return True
        except Exception as e:
            logger.error(f"Error building services for {account_email}: {e}")
            return False

    def get_connected_accounts(self) -> List[str]:
        """Returns a list of successfully authenticated email accounts."""
        return self.connected_accounts
    def _get_services_for_account(self, account: Optional[str] = None) -> Tuple[Any, Any, str]:
        """
        Retrieves the Gmail service, People service, and resolved account email.
        Handles default logic for single-account users and ambiguity for multi-account users.
        """
        if account:
            gmail_service = self.services.get(account)
            if not gmail_service:
                raise ValueError(f"Account '{account}' is not authenticated or does not exist for this user.")
            people_service = self.people_services.get(account)
            return gmail_service, people_service, account

        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            gmail_service = self.services[default_account]
            people_service = self.people_services[default_account]
            return gmail_service, people_service, default_account
        
        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Gmail accounts found for this user.")
        
        raise ValueError(
            "This user has multiple connected accounts. Please specify which account to use "
            f"with the 'account' parameter. Available accounts: {self.connected_accounts}"
        )
    async def send_email(self, recipient: str, subject: str, body: str, *, from_account: Optional[str] = None) -> Dict:
        """Sends an email, defaulting to the single account if available."""
        gmail_service, people_service, resolved_account = self._get_services_for_account(from_account)

        message = EmailMessage()
        if '<' in body and '>' in body:
            html_body = body.replace('\n', '<br>')
            message.add_alternative(html_body, subtype='html')
        else:
            message.set_content(body)
        
        message['To'] = recipient
        message['From'] = resolved_account # Use the resolved account
        message['Subject'] = subject
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message_request = {'raw': encoded_message}
        
        sent_message = gmail_service.users().messages().send(
            userId='me',
            body=create_message_request
        ).execute()
        
        return {"email_id": sent_message['id']}

    async def get_emails_from_sender(self, sender_email: str, *, account: Optional[str] = None, max_results: int = 10) -> List[Dict]:
        """Fetches emails from a sender, defaulting to the single account if available."""
        gmail_service, people_service, resolved_account = self._get_services_for_account(account)

        query = f"from:{sender_email}"
        results = gmail_service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return []

        email_list = []
        for msg in messages:
            try:
                msg_data = gmail_service.users().messages().get(userId='me', id=msg['id']).execute()
                headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
                email_list.append({
                    "subject": headers.get('Subject', 'No Subject'),
                    "snippet": msg_data.get('snippet', '')
                })
            except HttpError as e:
                logger.error(f"Error fetching message {msg['id']} for account {resolved_account}: {e}")
                continue
        return email_list

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
    async def search_emails(self, query: str, *, account: Optional[str] = None, max_results: int = 10) -> List[Dict]:
        """Searches emails, defaulting to the single account if available."""
        gmail_service, people_service, resolved_account = self._get_services_for_account(account)

        results = gmail_service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return []

        email_list = []
        for msg in messages:
            try:
                msg_data = gmail_service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
                headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
                email_list.append({
                    "id": msg_data['id'],
                    "subject": headers.get('Subject', 'No Subject'),
                    "snippet": msg_data.get('snippet', '')
                })
            except HttpError as e:
                logger.error(f"Error fetching metadata for message {msg['id']} for account {resolved_account}: {e}")
                continue
        return email_list

    async def find_contact_email(self, name: str, *, account: Optional[str] = None) -> List[Dict]:
        """
        Searches a specific Google Contacts account for a person's email address by name.
        Defaults to the single connected account if available.
        """
        _, people_service, resolved_account = self._get_services_for_account(account)

        if not people_service:
            # This case is rare due to the check in the helper, but it's good defensive programming.
            raise Exception(f"Google People API service not initialized for account {resolved_account}.")

        logger.info(f"Searching for contact '{name}' in account {resolved_account} for user {self.user_id}")
        try:
            results = people_service.people().searchContacts(
                query=name,
                readMask="names,emailAddresses,nicknames"
            ).execute()
            contacts = results.get('results', [])

            if not contacts:
                logger.info(f"No primary contacts found for '{name}'. Searching other contacts for account {resolved_account}.")
                results = people_service.otherContacts().search(
                    query=f"{name}*",
                    readMask="names,emailAddresses,nicknames"
                ).execute()
                contacts = results.get('results', [])

            if not contacts:
                logger.info(f"No contacts found for '{name}' in account {resolved_account}.")
                return []

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
        except HttpError as e:
            logger.error(f"Failed to search contacts for account {resolved_account}: {e}")
            return []

    async def setup_push_notifications(self, topic_name: str, *, account: Optional[str] = None) -> Optional[Dict]:
        """Sets up Gmail push notifications for a specific account."""
        service, _, resolved_account = self._get_services_for_account(account)
        
        request = {
            'labelIds': ['INBOX'],
            'topicName': topic_name
        }
        try:
            result = service.users().watch(userId='me', body=request).execute()
            logger.info(f"Gmail push notifications setup for account {resolved_account}. History ID: {result.get('historyId')}")
            return result
        except Exception as e:
            logger.error(f"Failed to setup Gmail push notifications for account {resolved_account}: {e}")
            return None

    async def stop_push_notifications(self, *, account: Optional[str] = None) -> bool:
        """Stops active Gmail push notifications for a specific account."""
        service, _, resolved_account = self._get_services_for_account(account)
        try:
            service.users().stop(userId='me').execute()
            logger.info(f"Gmail push notifications stopped for account {resolved_account}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop Gmail push notifications for account {resolved_account}: {e}")
            return False

    def get_changed_message_ids_since(
        self,
        start_history_id: str,
        *,
        account: Optional[str] = None,
        history_types: Optional[List[str]] = None,
    ) -> Tuple[List[str], Optional[str]]:
        """Gets new message IDs from a specific account since a given history ID."""
        service, _, resolved_account = self._get_services_for_account(account)
        history_types = history_types or ["messageAdded"]
        msg_ids: List[str] = []
        page_token = None
        max_history_id_seen: Optional[int] = None
        try:
            while True:
                req = service.users().history().list(
                    userId=self.gmail_user_id,
                    startHistoryId=str(start_history_id),
                    pageToken=page_token,
                    historyTypes=history_types,
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
            logger.error(f"Error fetching Gmail history for account {resolved_account}: {e}")
            return [], None # Return empty list on error, don't update checkpoint

        seen, deduped = set(), []
        for mid in msg_ids:
            if mid not in seen:
                seen.add(mid)
                deduped.append(mid)

        new_checkpoint = str(max_history_id_seen) if max_history_id_seen is not None else None
        return deduped, new_checkpoint

    def get_messages_by_ids(self, message_ids: List[str], *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets full message details for a list of IDs from a specific account."""
        service, _, _ = self._get_services_for_account(account)
        out = []
        for mid in message_ids:
            try:
                msg = service.users().messages().get(userId=self.gmail_user_id, id=mid, format="full").execute()
                out.append(msg)
            except HttpError as e:
                logger.error(f"Could not retrieve message ID {mid}: {e}")
                continue
        return out

    async def _download_and_store_attachment(
        self,
        *,
        user_record: Dict[str, Any],
        message_id: str,
        part: Dict[str, Any],
        account: str, # Account is required here as it's an internal method
    ) -> Dict[str, Any]:
        """Downloads a single attachment to blob storage for a specific account."""
        service, _, resolved_account = self._get_services_for_account(account)
        body = part.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            return {}

        att = service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        data_b64 = att.get("data")
        if not data_b64:
            return {}

        raw_bytes = base64.urlsafe_b64decode(data_b64.encode("utf-8"))
        filename = part.get("filename") or "attachment"
        mime_type = part.get("mimeType") or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Account is now part of the blob path to prevent collisions
        blob_name = f"{str(user_record['_id'])}/gmail/{resolved_account}/{message_id}/{filename}"
        blob_path = await upload_bytes_to_blob_storage(raw_bytes, blob_name, content_type=mime_type)

        document_entry = {
            "user_id": ObjectId(user_record["_id"]),
            "platform": "gmail",
            "connected_account": resolved_account, # Store which account it came from
            "platform_file_id": attachment_id,
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
    async def _collect_attachments_normalized(
        self,
        *,
        user_record: Dict[str, Any],
        message: Dict[str, Any],
        account: str, # Account is required here
    ) -> List[Dict[str, Any]]:      
        results: List[Dict[str, Any]] = []
        
        def _walk_parts(p: Dict[str, Any]):
            yield p
            for child in p.get("parts", []) or []:
                yield from _walk_parts(child)

        for p in _walk_parts(message.get("payload") or {}):
            filename = p.get("filename") or ""
            body = p.get("body", {}) or {}
            if filename and body.get("attachmentId"):
                file_rec = await self._download_and_store_attachment(
                    user_record=user_record,
                    message_id=message["id"],
                    part=p,
                    account=account, # Pass the account down
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
        account: Optional[str] = None,
        command_prefix: str = "",
    ) -> Dict[str, Any]:
        """Normalizes a raw Gmail message into a standard format for a specific account."""
        # We don't need the service objects here, just the resolved account name
        _, _, resolved_account = self._get_services_for_account(account)
        
        headers = self._headers_to_map(message.get("payload", {}).get("headers", []))
        plain, html = self._walk_parts_collect_bodies(message.get("payload", {}) or {})
        body_text = plain or (self._strip_html(html) if html else "")
        if command_prefix:
            body_text = f"{command_prefix}\n\n{body_text}" if body_text else command_prefix

        files = await self._collect_attachments_normalized(
            user_record=user_record,
            message=message,
            account=resolved_account, # Use the resolved account
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
                "connected_account": resolved_account, # Add account for context
                "gmail_message_id": message.get("id"),
                "gmail_thread_id": message.get("threadId"),
                "history_id": message.get("historyId"),
            },
        }
        return normalized
    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetches recent emails, defaulting to the single account if available."""
        service, _, resolved_account = self._get_services_for_account(account)
        
        try:
            is_allowed, remaining = rate_limiter.check_limit(self.user_id, "emails")
            if not is_allowed:
                logger.error(f"Email rate limit exceeded for user {self.user_id}")
                return []

            since_str = (since or (datetime.utcnow() - timedelta(days=7))).strftime('%Y/%m/%d')
            query = f'after:{since_str}'
            
            result = service.users().messages().list(
                userId=self.gmail_user_id, q=query, maxResults=min(settings.MAX_EMAILS, remaining)
            ).execute()
            
            messages = result.get('messages', [])
            detailed_messages, attachment_count = [], 0

            for message in messages[:settings.MAX_EMAILS]:
                if attachment_count >= settings.MAX_EMAIL_ATTACHMENTS:
                    break
                
                try:
                    msg_detail = service.users().messages().get(
                        userId=self.gmail_user_id, id=message['id'], format='full'
                    ).execute()
                    
                    formatted_message = await self._format_message(msg_detail)
                    msg_attachments = len(formatted_message.get('attachments', []))

                    if attachment_count + msg_attachments <= settings.MAX_EMAIL_ATTACHMENTS:
                        detailed_messages.append(formatted_message)
                        attachment_count += msg_attachments
                        rate_limiter.increment_usage(self.user_id, "emails", 1)
                        if msg_attachments > 0:
                            rate_limiter.increment_usage(self.user_id, "email_attachments", msg_attachments)
                except HttpError as e:
                    logger.error(f"Error fetching message {message['id']} for {resolved_account}: {e}")
                    continue
            
            return detailed_messages
        except Exception as e:
            logger.error(f"Error fetching Gmail messages for {resolved_account}: {e}")
            return []

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
    async def get_message_by_id(self, message_id: str, *, account: Optional[str] = None) -> Dict:
        """
        Retrieves and formats the full content of a single email by its ID.
        """
        service, _, resolved_account = self._get_services_for_account(account)
        try:
            message = service.users().messages().get(
                userId=self.gmail_user_id, id=message_id, format='full'
            ).execute()
            # Reuse the existing formatting method to return a clean, structured response
            return await self._format_message(message)
        except HttpError as e:
            logger.error(f"Error fetching message ID {message_id} for {resolved_account}: {e}")
            raise Exception(f"Could not retrieve email with ID {message_id}.") from e

    async def reply_to_message(self, original_message_id: str, body: str, reply_all: bool = False, *, account: Optional[str] = None) -> Dict:
        """
        Constructs and sends a reply to an existing email.
        """
        service, _, resolved_account = self._get_services_for_account(account)
        
        try:
            # 1. Fetch the original message to get necessary headers
            original_message = service.users().messages().get(
                userId=self.gmail_user_id, id=original_message_id, format='metadata'
            ).execute()
            
            headers = {h['name']: h['value'] for h in original_message['payload']['headers']}
            
            # 2. Construct the reply headers
            reply_subject = headers.get('Subject', '')
            if not reply_subject.lower().startswith('re:'):
                reply_subject = f"Re: {reply_subject}"

            reply = EmailMessage()
            reply['Subject'] = reply_subject
            reply['From'] = resolved_account
            reply['In-Reply-To'] = headers.get('Message-ID')
            reply['References'] = headers.get('References', '') + ' ' + headers.get('Message-ID')

            # 3. Determine recipients
            original_from = headers.get('From', '')
            if reply_all:
                original_to = headers.get('To', '')
                original_cc = headers.get('Cc', '')
                recipients = {original_from}
                if original_to: recipients.update(re.split(r', *', original_to))
                if original_cc: recipients.update(re.split(r', *', original_cc))
                # Remove own address from the recipients
                recipients.discard(resolved_account) 
                reply['To'] = ", ".join(recipients)
            else:
                reply['To'] = original_from
            
            reply.set_content(body)

            # 4. Encode and send the message
            encoded_message = base64.urlsafe_b64encode(reply.as_bytes()).decode()
            create_message_request = {
                'raw': encoded_message,
                'threadId': original_message['threadId'] # Ensures it stays in the same conversation
            }
            
            sent_message = service.users().messages().send(
                userId=self.gmail_user_id,
                body=create_message_request
            ).execute()
            
            return {"status": "success", "message_id": sent_message['id']}
        except HttpError as e:
            logger.error(f"Error replying to message {original_message_id} from {resolved_account}: {e}")
            raise Exception("Failed to send the reply.") from e


    async def modify_message_labels(self, message_id: str, labels_to_add: Optional[List[str]] = None, labels_to_remove: Optional[List[str]] = None, *, account: Optional[str] = None) -> Dict:
        """
        Adds or removes labels from a message. Used for archiving, marking as read/unread, etc.
        """
        service, _, resolved_account = self._get_services_for_account(account)
        
        body = {}
        if labels_to_add:
            body['addLabelIds'] = labels_to_add
        if labels_to_remove:
            body['removeLabelIds'] = labels_to_remove
            
        if not body:
            return {"status": "no_action", "message": "No labels specified to add or remove."}
        
        try:
            result = service.users().messages().modify(
                userId=self.gmail_user_id, id=message_id, body=body
            ).execute()
            return {"status": "success", "id": result['id'], "labels": result['labelIds']}
        except HttpError as e:
            logger.error(f"Error modifying labels for message {message_id} in {resolved_account}: {e}")
            raise Exception("Failed to modify the email's labels.") from e

    async def archive_message(self, message_id: str, *, account: Optional[str] = None) -> Dict:
        """
        Archives a message by removing the 'INBOX' label.
        This is a convenience wrapper around modify_message_labels.
        """
        return await self.modify_message_labels(
            message_id=message_id,
            labels_to_remove=['INBOX'],
            account=account
        )

    async def mark_as_unread(self, message_id: str, *, account: Optional[str] = None) -> Dict:
        """
        Marks a message as unread by adding the 'UNREAD' label.
        """
        return await self.modify_message_labels(
            message_id=message_id,
            labels_to_add=['UNREAD'],
            account=account
        )

    async def add_star(self, message_id: str, *, account: Optional[str] = None) -> Dict:
        """
        Stars a message by adding the 'STARRED' label.
        """
        return await self.modify_message_labels(
            message_id=message_id,
            labels_to_add=['STARRED'],
            account=account
        )

    async def remove_star(self, message_id: str, *, account: Optional[str] = None) -> Dict:
        """
        Removes the star from a message by removing the 'STARRED' label.
        """
        return await self.modify_message_labels(
            message_id=message_id,
            labels_to_remove=['STARRED'],
            account=account
        )

    async def move_to_spam(self, message_id: str, *, account: Optional[str] = None) -> Dict:
        """
        Moves a message to spam by adding the 'SPAM' label.
        """
        return await self.modify_message_labels(
            message_id=message_id,
            labels_to_add=['SPAM'],
            account=account
        )

    async def move_to_trash(self, message_id: str, *, account: Optional[str] = None) -> Dict:
        """
        Moves a message to trash by adding the 'TRASH' label.
        """
        return await self.modify_message_labels(
            message_id=message_id,
            labels_to_add=['TRASH'],
            account=account
        )

    async def create_draft(self, recipient: str, subject: str, body: str, *, account: Optional[str] = None) -> Dict:
        """
        Creates a draft email in Gmail.
        """
        service, _, resolved_account = self._get_services_for_account(account)

        message = EmailMessage()
        if '<' in body and '>' in body:
            html_body = body.replace('\n', '<br>')
            message.add_alternative(html_body, subtype='html')
        else:
            message.set_content(body)

        message['To'] = recipient
        message['From'] = resolved_account
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft_body = {
            'message': {
                'raw': encoded_message
            }
        }

        try:
            draft = service.users().drafts().create(
                userId='me',
                body=draft_body
            ).execute()
            return {
                "draft_id": draft['id'],
                "message_id": draft['message']['id'],
                "status": "draft_created"
            }
        except HttpError as e:
            logger.error(f"Error creating draft for {resolved_account}: {e}")
            raise Exception("Failed to create draft.") from e

    async def list_labels(self, *, account: Optional[str] = None) -> List[Dict]:
        """
        Lists all labels (folders) in the Gmail account.
        """
        service, _, resolved_account = self._get_services_for_account(account)

        try:
            results = service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            return [
                {
                    "id": label['id'],
                    "name": label['name'],
                    "type": label.get('type', 'user')
                }
                for label in labels
            ]
        except HttpError as e:
            logger.error(f"Error listing labels for {resolved_account}: {e}")
            raise Exception("Failed to list labels.") from e

    async def add_label_to_message(self, message_id: str, label_name: str, *, account: Optional[str] = None) -> Dict:
        """
        Adds a specific label to a message. Creates the label if it doesn't exist.
        """
        service, _, resolved_account = self._get_services_for_account(account)

        try:
            # First, check if label exists
            labels = await self.list_labels(account=account)
            label_id = None

            for label in labels:
                if label['name'].lower() == label_name.lower():
                    label_id = label['id']
                    break

            # If label doesn't exist, create it
            if not label_id:
                label_body = {
                    'name': label_name,
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                }
                created_label = service.users().labels().create(
                    userId='me',
                    body=label_body
                ).execute()
                label_id = created_label['id']
                logger.info(f"Created new label '{label_name}' for {resolved_account}")

            # Add the label to the message
            return await self.modify_message_labels(
                message_id=message_id,
                labels_to_add=[label_id],
                account=account
            )
        except HttpError as e:
            logger.error(f"Error adding label to message for {resolved_account}: {e}")
            raise Exception(f"Failed to add label '{label_name}'.") from e

    async def remove_label_from_message(self, message_id: str, label_name: str, *, account: Optional[str] = None) -> Dict:
        """
        Removes a specific label from a message.
        """
        service, _, resolved_account = self._get_services_for_account(account)

        try:
            # Find the label ID
            labels = await self.list_labels(account=account)
            label_id = None

            for label in labels:
                if label['name'].lower() == label_name.lower():
                    label_id = label['id']
                    break

            if not label_id:
                return {
                    "status": "error",
                    "message": f"Label '{label_name}' not found."
                }

            # Remove the label from the message
            return await self.modify_message_labels(
                message_id=message_id,
                labels_to_remove=[label_id],
                account=account
            )
        except HttpError as e:
            logger.error(f"Error removing label from message for {resolved_account}: {e}")
            raise Exception(f"Failed to remove label '{label_name}'.") from e
