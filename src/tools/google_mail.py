from typing import List
from langchain_core.tools import tool
from src.integrations.email.gmail_client import GmailIntegration
from src.tools.tool_types import ToolExecutionResponse
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
            signed_body = (body or "") + '\n\nEmail directive handled by <a href="https://app.mypraxos.com">My Praxos</a>'
            result = await gmail_integration.send_email(recipient, subject, signed_body, from_account=from_account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="There was an error sending the email.")

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
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="There was an error sending the reply.")

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
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="An error occurred during the email search.")

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
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Could not retrieve the email's content.")

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
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"An error occurred fetching emails from {sender_email}.")

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
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"An error occurred while searching for '{name}'.")

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
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="The email could not be archived.")

    @tool
    async def mark_email_as_read(
        message_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Marks a specific email as read by removing the 'UNREAD' label. Provide the email's message ID."""
        try:
            # NOTE: Assumes you will add a `modify_message_labels` method.
            result = await gmail_integration.modify_message_labels(
                message_id=message_id, 
                labels_to_remove=['UNREAD'],
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="The email could not be marked as read.")


    accounts = gmail_integration.get_connected_accounts()
    if not accounts:
        return [] 

    all_tools = [
        send_email, reply_to_email, search_gmail, get_email_content, 
        get_emails_from_sender, find_contact_email, archive_email, mark_email_as_read
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