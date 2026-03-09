from typing import List
from langchain_core.tools import tool
from src.integrations.email.gmail_client import GmailIntegration
from src.integrations.scope_validator import InsufficientScopeError
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from typing import Optional

logger = setup_logger(__name__)


def create_gmail_tools(gmail_integration: GmailIntegration, tool_registry, conversation_id: Optional[str] = None) -> List:
    """
    Creates a comprehensive set of Gmail and Google Contacts tools.
    The tools are dynamically configured based on the user's connected accounts.
    """



    @tool
    async def send_google_email(
        recipient: str, 
        subject: str, 
        body: str, 
        from_account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Sends an email using the user's Gmail account."""
        try:
            from src.utils.constant import NO_WATERMARK_USER_IDS
            signed_body = (body if body else "")
            if gmail_integration.user_id not in NO_WATERMARK_USER_IDS:
                signed_body += '\n\nEmail directive handled by <a href="https://app.mypraxos.com/log-in">My Praxos</a>'            
            result = await gmail_integration.send_email(recipient, subject, signed_body, from_account=from_account)
            from src.utils.constant import NO_WATERMARK_USER_IDS

            singed_body = (body if body else "")
            if gmail_integration.user_id not in NO_WATERMARK_USER_IDS:
                singed_body += '\n\nEmail directive handled by <a href="https://app.mypraxos.com/log-in">My Praxos</a>'
            
            result = await gmail_integration.send_email(recipient, subject, singed_body)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="send_email",
                exception=e,
                integration="Gmail",
                context={"recipient": recipient}
            )

    @tool
    async def reply_to_google_email(
        original_message_id: str,
        body: str,
        reply_all: bool = False,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Replies to a specific email. You MUST provide the ID of the original email to reply to.
        Set 'reply_all' to True to reply to everyone on the thread.
        """
        try:
            signed_body = (body or "") + '\n\nReplied via <a href="https://app.mypraxos.com">My Praxos</a>'
            # NOTE: Assumes you will add a `reply_to_message` method to your GmailIntegration class.
            result = await gmail_integration.reply_to_message(
                original_message_id=original_message_id,
                body=signed_body,
                reply_all=reply_all,
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error replying to email ID {original_message_id}: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="reply_to_email",
                exception=e,
                integration="Gmail",
                context={"original_message_id": original_message_id}
            )

    # --- Information Retrieval Tools ---

    @tool
    async def search_google_email(
        query: str, 
        max_results: int = 10,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Searches for emails in the user's Gmail account using a specific query.
        Returns a list of emails with their ID, subject, and snippet.
        Example queries: 'from:elon@musk.com subject:starship', 'dinner plans', 'is:unread'.
        """
        try:
            emails = await gmail_integration.search_emails(query, max_results=max_results, account=account)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="search_gmail",
                exception=e,
                integration="Gmail",
                context={"query": query}
            )

    @tool
    async def get_google_email_content(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Retrieves the full content (body, attachments, sender, etc.) of a specific email using its message ID.
        Use this tool AFTER finding an email with 'search_gmail' to read its full contents.
        """
        try:
            # NOTE: Assumes you will add a `get_message_by_id` method to your GmailIntegration class.
            logger.info(f"Attempting to retrieve email content. Message ID: {message_id}, Account: {account}")
            email_content = await gmail_integration.get_message_by_id(message_id=message_id, account=account)
            logger.info(f"Successfully retrieved email content for Message ID: {message_id}. Email subject: {email_content.get('subject', 'N/A')}")
            return ToolExecutionResponse(status="success", result=email_content)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_google_email_content",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id, "resource_type": "email"}
            )

    @tool
    async def retrieve_google_email_attachment(
        message_id: str,
        attachment_id: str,
        filename: str,
        mime_type: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Downloads a specific email attachment and loads it into the conversation context so you can analyze it.
        You MUST provide the filename and mime_type exactly as they appear in the email metadata.
        """
        try:
            logger.info(f"Attempting to retrieve attachment. Message ID: {message_id}, Attachment ID: {attachment_id}, Filename: {filename}, MIME Type: {mime_type}, Account: {account}")
            from src.services.user_service import user_service
            user_record = user_service.get_user_by_id(gmail_integration.user_id)
            if not user_record:
                raise Exception("User not found.")

            file_rec = await gmail_integration.retrieve_and_store_attachment(
                user_record=user_record,
                message_id=message_id,
                attachment_id=attachment_id,
                filename=filename,
                mime_type=mime_type,
                account=account
            )
            
            if not file_rec:
                raise Exception("Failed to download attachment or attachment was empty.")
            logger.info(f"Successfully retrieved attachment and stored in blob storage. Blob path: {file_rec.get('blob_path')}, Inserted ID: {file_rec.get('inserted_id')}")
            media_id = None
            if conversation_id:
                from src.core.media_bus import media_bus
                
                file_type = "document"
                if mime_type.startswith("image/"):
                    file_type = "image"
                elif mime_type.startswith("audio/"):
                    file_type = "audio"
                elif mime_type.startswith("video/"):
                    file_type = "video"
                    
                media_id = await media_bus.add_media(
                    conversation_id=conversation_id,
                    url="",  # No direct URL for blob storage items yet
                    file_name=filename,
                    file_type=file_type,
                    description=f"Email attachment: {filename}",
                    source="gmail",
                    blob_path=file_rec.get("blob_path"),
                    mime_type=mime_type,
                    metadata={"inserted_id": file_rec.get("inserted_id")}
                )

            return ToolExecutionResponse(
                status="success", 
                result=f"Successfully retrieved attachment '{filename}' and loaded it into the media bus. you can request it to be put into the context via its Media ID, which you can use to access it from the bus to put it in context. the media is : {media_id}, "
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="retrieve_email_attachment",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id, "attachment_id": attachment_id}
            )

    @tool
    async def get_google_emails_from_sender(
        sender_email: str, 
        max_results: int = 10,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Fetches the most recent emails from a specific sender in the user's Gmail account."""
        try:
            emails = await gmail_integration.get_emails_from_sender(sender_email, max_results=max_results, account=account)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_emails_from_sender",
                exception=e,
                integration="Gmail",
                context={"sender_email": sender_email}
            )

    @tool
    async def find_google_contact_email(
        name: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Searches the user's Google Contacts for a person's email address by their name."""
        try:
            contacts = await gmail_integration.find_contact_email(name, account=account)
            if not contacts:
                return ToolExecutionResponse(status="success", result=f"No contacts found matching '{name}'.")
            return ToolExecutionResponse(status="success", result=contacts)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="find_contact_email",
                exception=e,
                integration="Google Contacts",
                context={"contact_name": name}
            )

    # --- Inbox Management Tools ---
    
    @tool
    async def archive_google_email(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Archives an email, moving it out of the inbox to the 'All Mail' folder. Provide the email's message ID."""
        try:
            # NOTE: Assumes you will add a `archive_message` method to GmailIntegration.
            result = await gmail_integration.archive_message(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="archive_email",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def mark_google_email_as_read(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Marks a specific email as read by removing the 'UNREAD' label. Provide the email's message ID."""
        try:
            result = await gmail_integration.modify_message_labels(
                message_id=message_id,
                labels_to_remove=['UNREAD'],
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="mark_email_as_read",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def mark_google_email_as_unread(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Marks a specific email as unread by adding the 'UNREAD' label. Provide the email's message ID."""
        try:
            result = await gmail_integration.mark_as_unread(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="mark_email_as_unread",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def star_google_email(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Stars an email by adding the 'STARRED' label. Provide the email's message ID."""
        try:
            result = await gmail_integration.add_star(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except InsufficientScopeError as e:
            # User-friendly error message for missing OAuth permissions
            logger.warning(f"Insufficient Gmail scopes for star_email: {e}")
            return ToolExecutionResponse(
                status="error",
                result=(
                    f"Unable to star email: Missing required Gmail permissions.\n\n"
                    f"To fix this, please reconnect your Gmail account at "
                    f"https://app.mypraxos.com/integrations and grant "
                    f"'Modify emails' permission.\n\n"
                    f"Technical details: {str(e)}"
                )
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="star_email",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def unstar_google_email(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Removes the star from an email by removing the 'STARRED' label. Provide the email's message ID."""
        try:
            result = await gmail_integration.remove_star(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="unstar_email",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def move_google_email_to_spam(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Moves an email to spam. Provide the email's message ID."""
        try:
            result = await gmail_integration.move_to_spam(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="move_email_to_spam",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def move_google_email_to_trash(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Moves an email to trash. Provide the email's message ID."""
        try:
            result = await gmail_integration.move_to_trash(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="move_email_to_trash",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def create_google_email_draft(
        recipient: str,
        subject: str,
        body: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Creates a draft email in Gmail without sending it. The draft can be edited and sent later."""
        try:
            result = await gmail_integration.create_draft(
                recipient=recipient,
                subject=subject,
                body=body,
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="create_email_draft",
                exception=e,
                integration="Gmail",
                context={"recipient": recipient, "subject": subject}
            )

    @tool
    async def list_google_email_labels(
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Lists all labels (folders) in the user's Gmail account, including system and custom labels."""
        try:
            result = await gmail_integration.list_labels(account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="list_gmail_labels",
                exception=e,
                integration="Gmail",
                context={}
            )

    @tool
    async def add_label_to_google_email(
        message_id: str,
        label_name: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Adds a label/folder to an email. Creates the label if it doesn't exist. Provide the email's message ID and label name."""
        try:
            result = await gmail_integration.add_label_to_message(
                message_id=message_id,
                label_name=label_name,
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="add_label_to_email",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id, "label_name": label_name}
            )

    @tool
    async def remove_label_from_google_email(
        message_id: str,
        label_name: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Removes a label/folder from an email. Provide the email's message ID and label name."""
        try:
            result = await gmail_integration.remove_label_from_message(
                message_id=message_id,
                label_name=label_name,
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="remove_label_from_email",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id, "label_name": label_name}
            )


    # Tool registry is passed in and already loaded
    accounts = gmail_integration.get_connected_accounts()
    if not accounts:
        return []

    @tool
    async def get_frequent_google_senders(days_back: int = 30, max_senders: int = 15, source_folder: str = "INBOX", account: Optional[str] = None) -> ToolExecutionResponse:
        """Analyzes a specific folder (defaults to 'INBOX') to find the most frequent email senders."""
        try:
            label_id = source_folder
            if source_folder.upper() not in ['INBOX', 'SPAM', 'TRASH', 'SENT', 'DRAFT']:
                labels = await gmail_integration.list_labels(account=account)
                for label in labels:
                    if label['name'].lower() == source_folder.lower():
                        label_id = label['id']
                        break
            else:
                label_id = source_folder.upper()

            senders = await gmail_integration.get_frequent_senders(days_back=days_back, max_senders=max_senders, source_folder=label_id, account=account)
            return ToolExecutionResponse(status="success", result=senders)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_frequent_google_senders",
                exception=e,
                integration="Gmail",
                context={"days_back": days_back, "source_folder": source_folder}
            )

    @tool
    async def create_google_email_rule(query: str, add_label_name: Optional[str] = None, archive: bool = False, trash: bool = False, account: Optional[str] = None) -> ToolExecutionResponse:
        """Creates an automatic Gmail filter (rule) to route incoming emails matching a query."""
        try:
            criteria = {'query': query}
            action = {}
            
            if add_label_name:
                # Find or create label
                labels = await gmail_integration.list_labels(account=account)
                label_id = None
                for label in labels:
                    if label['name'].lower() == add_label_name.lower():
                        label_id = label['id']
                        break
                if not label_id:
                    new_label = await gmail_integration.create_label(add_label_name, account=account)
                    label_id = new_label['id']
                action['addLabelIds'] = [label_id]
                
            if archive:
                action['removeLabelIds'] = ['INBOX']
            if trash:
                action['addLabelIds'] = action.get('addLabelIds', []) + ['TRASH']
                
            if not action:
                return ToolExecutionResponse(status="error", result="You must specify an action: add_label_name, archive, or trash.")

            rule = await gmail_integration.create_filter(criteria, action, account=account)
            return ToolExecutionResponse(status="success", result=rule)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="create_google_email_rule",
                exception=e,
                integration="Gmail",
                context={"query": query}
            )

    @tool
    async def move_google_emails_by_sender(sender_email: str, destination_folder: str, source_folder: str = "INBOX", max_results: int = 1000, account: Optional[str] = None) -> ToolExecutionResponse:
        """Finds all emails from a specific sender in a source folder and moves them to a destination folder."""
        try:
            # 1. Resolve destination folder/label
            add_label_ids = []
            remove_label_ids = []
            
            dest_lower = destination_folder.lower()
            if dest_lower in ['trash', 'deleteditems']:
                add_label_ids = ['TRASH']
            elif dest_lower == 'archive':
                remove_label_ids = ['INBOX']
            elif dest_lower == 'spam':
                add_label_ids = ['SPAM']
            else:
                # Custom label - try to find it or create it
                labels = await gmail_integration.list_labels(account=account)
                label_id = None
                for label in labels:
                    if label['name'].lower() == dest_lower:
                        label_id = label['id']
                        break
                
                if not label_id:
                    new_label = await gmail_integration.create_label(destination_folder, account=account)
                    label_id = new_label['id']
                
                add_label_ids = [label_id]
                remove_label_ids = ['INBOX'] # usually moving to a custom folder implies archiving from inbox
                
            # 2. Resolve source folder/label
            source_label_id = source_folder
            if source_folder.upper() not in ['INBOX', 'SPAM', 'TRASH', 'SENT', 'DRAFT']:
                labels = await gmail_integration.list_labels(account=account)
                for label in labels:
                    if label['name'].lower() == source_folder.lower():
                        source_label_id = label['id']
                        break
            else:
                source_label_id = source_folder.upper()

            # 3. Fetch emails
            emails = await gmail_integration.get_emails_from_sender(sender_email, account=account, max_results=max_results, source_folder=source_label_id)
            if not emails:
                return ToolExecutionResponse(status="success", result=f"No emails found from {sender_email} in {source_folder}.")

            # 4. Bulk modify
            message_ids = [email['id'] for email in emails]
            result = await gmail_integration.bulk_modify_messages(message_ids, add_label_ids=add_label_ids, remove_label_ids=remove_label_ids, account=account)
            
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="move_google_emails_by_sender",
                exception=e,
                integration="Gmail",
                context={"sender_email": sender_email, "destination_folder": destination_folder, "source_folder": source_folder}
            )

    @tool
    async def categorize_google_emails_by_sender(sender_email: str, label_name: str, source_folder: str = "INBOX", max_results: int = 1000, account: Optional[str] = None) -> ToolExecutionResponse:
        """Finds all emails from a specific sender in a source folder and applies a label to them without archiving them."""
        try:
            # 1. Find or create destination label
            labels = await gmail_integration.list_labels(account=account)
            label_id = None
            for label in labels:
                if label['name'].lower() == label_name.lower():
                    label_id = label['id']
                    break
            
            if not label_id:
                new_label = await gmail_integration.create_label(label_name, account=account)
                label_id = new_label['id']
                
            # 2. Resolve source folder/label
            source_label_id = source_folder
            if source_folder.upper() not in ['INBOX', 'SPAM', 'TRASH', 'SENT', 'DRAFT']:
                for label in labels:
                    if label['name'].lower() == source_folder.lower():
                        source_label_id = label['id']
                        break
            else:
                source_label_id = source_folder.upper()
            
            # 3. Fetch emails
            emails = await gmail_integration.get_emails_from_sender(sender_email, account=account, max_results=max_results, source_folder=source_label_id)
            if not emails:
                return ToolExecutionResponse(status="success", result=f"No emails found from {sender_email} in {source_folder}.")

            # 4. Bulk modify
            message_ids = [email['id'] for email in emails]
            result = await gmail_integration.bulk_modify_messages(message_ids, add_label_ids=[label_id], account=account)
            
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="categorize_google_emails_by_sender",
                exception=e,
                integration="Gmail",
                context={"sender_email": sender_email, "label_name": label_name, "source_folder": source_folder}
            )

    all_tools = [
        send_google_email, reply_to_google_email, search_google_email, get_google_email_content,
        retrieve_google_email_attachment, get_google_emails_from_sender, find_google_contact_email, archive_google_email, mark_google_email_as_read,
        mark_google_email_as_unread, star_google_email, unstar_google_email, move_google_email_to_spam,
        move_google_email_to_trash, create_google_email_draft, list_google_email_labels,
        add_label_to_google_email, remove_label_from_google_email,
        get_frequent_google_senders, create_google_email_rule, move_google_emails_by_sender, categorize_google_emails_by_sender
    ]

    # Apply descriptions from YAML database
    # Note: send_google_email and reply_to_google_email use 'from_account', others use 'account'
    for t in all_tools:
        param_name = 'from_account' if t.name in ["send_google_email", "reply_to_google_email"] else 'account'
        tool_registry.apply_descriptions_to_tools([t], accounts=accounts, account_param_name=param_name)

    return all_tools