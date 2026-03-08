from typing import List
from langchain_core.tools import tool
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_outlook_tools(outlook_client: MicrosoftGraphIntegration, tool_registry) -> List:
    """Create Outlook-related tools"""

    @tool
    async def send_outlook_email(recipient: str, subject: str, body: str) -> ToolExecutionResponse:
        """Sends an email using Outlook."""
        try:
            await outlook_client.send_email(recipient, subject, body)
            return ToolExecutionResponse(status="success", result="Email sent successfully.")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="send_outlook_email",
                exception=e,
                integration="Microsoft Outlook",
                context={"recipient": recipient}
            )
    
    @tool 
    async def fetch_outlook_calendar_events(time_min: str, time_max: str) -> ToolExecutionResponse:
        """Fetches calendar events from Outlook."""
        try:
            events = await outlook_client.get_calendar_events(time_min, time_max)
            return ToolExecutionResponse(status="success", result=events)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="fetch_outlook_calendar_events",
                exception=e,
                integration="Microsoft Outlook"
            )

    @tool
    async def get_outlook_emails_from_sender(sender_email: str, max_results: int = 10) -> ToolExecutionResponse:
        """Fetches the most recent emails from a specific sender in the user's Outlook account."""
        try:
            emails = await outlook_client.get_emails_from_sender(sender_email, max_results)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_outlook_emails_from_sender",
                exception=e,
                integration="Microsoft Outlook",
                context={"sender_email": sender_email}
            )

    @tool
    async def find_outlook_contact_email(name: str) -> ToolExecutionResponse:
        """Searches the user's Outlook contacts for a person's email address by their name."""
        try:
            contacts = await outlook_client.find_contact_email(name)
            if not contacts:
                return ToolExecutionResponse(status="success", result=f"No contacts found matching the name '{name}'.")
            return ToolExecutionResponse(status="success", result=contacts)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="find_outlook_contact_email",
                exception=e,
                integration="Microsoft Outlook",
                context={"contact_name": name}
            )

    @tool
    async def mark_outlook_email_read(message_id: str, is_read: bool = True) -> ToolExecutionResponse:
        """Marks an email as read or unread."""
        try:
            await outlook_client.mark_email_read(message_id, is_read)
            status = "read" if is_read else "unread"
            return ToolExecutionResponse(status="success", result=f"Email successfully marked as {status}.")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="mark_outlook_email_read",
                exception=e,
                integration="Microsoft Outlook",
                context={"message_id": message_id}
            )

    @tool
    async def categorize_outlook_email(message_id: str, categories: List[str]) -> ToolExecutionResponse:
        """Adds or removes categories from an email."""
        try:
            await outlook_client.categorize_email(message_id, categories)
            return ToolExecutionResponse(status="success", result=f"Email successfully categorized with: {categories}")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="categorize_outlook_email",
                exception=e,
                integration="Microsoft Outlook",
                context={"message_id": message_id}
            )

    @tool
    async def move_outlook_email(message_id: str, destination_folder_id: str) -> ToolExecutionResponse:
        """Moves an email to a different folder."""
        try:
            await outlook_client.move_email(message_id, destination_folder_id)
            return ToolExecutionResponse(status="success", result=f"Email successfully moved to folder: {destination_folder_id}")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="move_outlook_email",
                exception=e,
                integration="Microsoft Outlook",
                context={"message_id": message_id}
            )

    @tool
    async def search_outlook_emails(query: str, max_results: int = 10) -> ToolExecutionResponse:
        """Searches the user's Outlook emails using a specific query string."""
        try:
            emails = await outlook_client.search_emails(query, max_results)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="search_outlook_emails",
                exception=e,
                integration="Microsoft Outlook",
                context={"query": query}
            )

    @tool
    async def get_outlook_email_content(message_id: str) -> ToolExecutionResponse:
        """Retrieves the full content of a specific Outlook email."""
        try:
            # Note: ms_user_id is not strictly required if we are querying /me/
            # but get_message_with_attachments signature requires it.
            # We pass outlook_client.user_id just to satisfy if needed, but the endpoint uses /me
            email_content = await outlook_client.get_message_with_attachments(ms_user_id="me", message_id=message_id)
            return ToolExecutionResponse(status="success", result=email_content)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_outlook_email_content",
                exception=e,
                integration="Microsoft Outlook",
                context={"message_id": message_id}
            )

    @tool
    async def list_outlook_folders() -> ToolExecutionResponse:
        """Lists all the mail folders in the user's Outlook mailbox (including custom ones) to get their folder IDs."""
        try:
            folders = await outlook_client.list_mail_folders()
            return ToolExecutionResponse(status="success", result=folders)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="list_outlook_folders",
                exception=e,
                integration="Microsoft Outlook"
            )

    @tool
    async def create_outlook_folder(display_name: str) -> ToolExecutionResponse:
        """Creates a new mail folder in the user's Outlook mailbox."""
        try:
            folder = await outlook_client.create_mail_folder(display_name)
            return ToolExecutionResponse(status="success", result=folder)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="create_outlook_folder",
                exception=e,
                integration="Microsoft Outlook",
                context={"display_name": display_name}
            )

    @tool
    async def create_outlook_rule(display_name: str, sequence: int, sender_contains: str, destination_folder: str) -> ToolExecutionResponse:
        """Creates an Outlook rule to automatically move incoming messages from a specific sender to a folder. You can provide the destination folder ID or its human-readable name."""
        try:
            folder_id = destination_folder
            well_known = ["inbox", "archive", "deleteditems", "junkemail", "drafts", "sentitems"]
            
            # Resolve folder ID if a friendly name was provided
            if destination_folder.lower() not in well_known and not destination_folder.startswith("AAMk"):
                folders = await outlook_client.list_mail_folders()
                for f in folders:
                    if f["name"].lower() == destination_folder.lower():
                        folder_id = f["id"]
                        break

            rule = await outlook_client.create_outlook_rule(display_name, sequence, sender_contains, folder_id)
            return ToolExecutionResponse(status="success", result=rule)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="create_outlook_rule",
                exception=e,
                integration="Microsoft Outlook",
                context={"display_name": display_name, "sender_contains": sender_contains, "destination_folder": destination_folder}
            )

    @tool
    async def bulk_categorize_outlook_emails(message_ids: List[str], categories: List[str]) -> ToolExecutionResponse:
        """Adds or removes categories from multiple emails simultaneously."""
        try:
            result = await outlook_client.bulk_categorize_emails(message_ids, categories)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="bulk_categorize_outlook_emails",
                exception=e,
                integration="Microsoft Outlook"
            )

    @tool
    async def bulk_move_outlook_emails(message_ids: List[str], destination_folder_id: str) -> ToolExecutionResponse:
        """Moves multiple emails simultaneously to a different folder. Provide the destination folder ID (e.g., 'archive', 'inbox', or a custom ID)."""
        try:
            result = await outlook_client.bulk_move_emails(message_ids, destination_folder_id)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="bulk_move_outlook_emails",
                exception=e,
                integration="Microsoft Outlook",
                context={"destination_folder_id": destination_folder_id}
            )

    @tool
    async def get_frequent_outlook_senders(days_back: int = 30, max_senders: int = 15) -> ToolExecutionResponse:
        """Analyzes the user's recent inbox and returns a list of the most frequent email senders."""
        try:
            senders = await outlook_client.get_frequent_senders(days_back=days_back, max_senders=max_senders)
            return ToolExecutionResponse(status="success", result=senders)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_frequent_outlook_senders",
                exception=e,
                integration="Microsoft Outlook",
                context={"days_back": days_back}
            )

    @tool
    async def move_outlook_emails_by_sender(sender_email: str, destination_folder: str, max_results: int = 50) -> ToolExecutionResponse:
        """Finds all emails from a specific sender and moves them to a folder (can provide folder name or ID)."""
        try:
            folder_id = destination_folder
            well_known = ["inbox", "archive", "deleteditems", "junkemail", "drafts", "sentitems"]
            
            # Resolve folder ID if a friendly name was provided
            if destination_folder.lower() not in well_known and not destination_folder.startswith("AAMk"):
                folders = await outlook_client.list_mail_folders()
                for f in folders:
                    if f["name"].lower() == destination_folder.lower():
                        folder_id = f["id"]
                        break
            
            emails = await outlook_client.get_emails_from_sender(sender_email, max_results=max_results)
            if not emails:
                return ToolExecutionResponse(status="success", result=f"No emails found from {sender_email}.")
                
            message_ids = [email['id'] for email in emails]
            result = await outlook_client.bulk_move_emails(message_ids, folder_id)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="move_outlook_emails_by_sender",
                exception=e,
                integration="Microsoft Outlook",
                context={"sender_email": sender_email, "destination_folder": destination_folder}
            )

    @tool
    async def categorize_outlook_emails_by_sender(sender_email: str, categories: List[str], max_results: int = 50) -> ToolExecutionResponse:
        """Finds all emails from a specific sender and applies categories to them."""
        try:
            emails = await outlook_client.get_emails_from_sender(sender_email, max_results=max_results)
            if not emails:
                return ToolExecutionResponse(status="success", result=f"No emails found from {sender_email}.")
                
            message_ids = [email['id'] for email in emails]
            result = await outlook_client.bulk_categorize_emails(message_ids, categories)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="categorize_outlook_emails_by_sender",
                exception=e,
                integration="Microsoft Outlook",
                context={"sender_email": sender_email, "categories": categories}
            )

    # Tool registry is passed in and already loaded
    all_tools = [
        send_outlook_email,
        fetch_outlook_calendar_events,
        get_outlook_emails_from_sender,
        find_outlook_contact_email,
        mark_outlook_email_read,
        categorize_outlook_email,
        move_outlook_email,
        search_outlook_emails,
        get_outlook_email_content,
        list_outlook_folders,
        create_outlook_folder,
        create_outlook_rule,
        bulk_categorize_outlook_emails,
        bulk_move_outlook_emails,
        move_outlook_emails_by_sender,
        categorize_outlook_emails_by_sender
    ]

    # Apply descriptions from YAML database (single account integration)
    tool_registry.apply_descriptions_to_tools(all_tools)

    return all_tools
