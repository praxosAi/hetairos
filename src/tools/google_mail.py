from typing import List
from langchain_core.tools import tool
from src.integrations.email.gmail_client import GmailIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from typing import Optional

logger = setup_logger(__name__)


def create_gmail_tools(gmail_integration: GmailIntegration) -> List:
    """
    Creates a comprehensive set of Gmail and Google Contacts tools.
    The tools are dynamically configured based on the user's connected accounts.
    """



    @tool
    async def send_email(
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
    async def reply_to_email(
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
    async def search_gmail(
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
    async def get_email_content(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Retrieves the full content (body, attachments, sender, etc.) of a specific email using its message ID.
        Use this tool AFTER finding an email with 'search_gmail' to read its full contents.
        """
        try:
            # NOTE: Assumes you will add a `get_message_by_id` method to your GmailIntegration class.
            email_content = await gmail_integration.get_message_by_id(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=email_content)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_email_content",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id, "resource_type": "email"}
            )

    @tool
    async def get_emails_from_sender(
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
    async def find_contact_email(
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
    async def archive_email(
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
    async def mark_email_as_read(
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
    async def mark_email_as_unread(
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
    async def star_email(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Stars an email by adding the 'STARRED' label. Provide the email's message ID."""
        try:
            result = await gmail_integration.add_star(message_id=message_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="star_email",
                exception=e,
                integration="Gmail",
                context={"message_id": message_id}
            )

    @tool
    async def unstar_email(
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
    async def move_email_to_spam(
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
    async def move_email_to_trash(
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
    async def create_email_draft(
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
    async def list_gmail_labels(
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
    async def add_label_to_email(
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
    async def remove_label_from_email(
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


    accounts = gmail_integration.get_connected_accounts()
    if not accounts:
        return []

    all_tools = [
        send_email, reply_to_email, search_gmail, get_email_content,
        get_emails_from_sender, find_contact_email, archive_email, mark_email_as_read,
        mark_email_as_unread, star_email, unstar_email, move_email_to_spam,
        move_email_to_trash, create_email_draft, list_gmail_labels,
        add_label_to_email, remove_label_from_email
    ]

    if len(accounts) == 1:
        
        user_email = accounts[0]
        for t in all_tools:
            t.description += f" The user's connected account is {user_email}."
    else:
        # If multiple accounts, instruct the AI that it MUST specify which one to use.
        account_list_str = ", ".join(f"'{acc}'" for acc in accounts)
        for t in all_tools:
            # Use 'from_account' for sending tools, 'account' for others.
            param = "'from_account'" if t.name in ["send_email", "reply_to_email"] else "'account'"
            t.description += (
                f" The user has multiple accounts. You MUST use the {param} parameter to specify which one to use. "
                f"Available accounts are: [{account_list_str}]."
            )
            
    return all_tools