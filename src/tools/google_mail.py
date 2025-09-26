from typing import List
from langchain_core.tools import tool
from src.integrations.email.gmail_client import GmailIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_gmail_tools(gmail_integration: GmailIntegration) -> List:
    """Creates Gmail and Google Contacts related tools."""

    @tool
    async def send_email(recipient: str, subject: str, body: str) -> ToolExecutionResponse:
        """Sends an email using Gmail API, from the user's Gmail ({user_email})."""
        try:
            singed_body = (body if body else "") + '\n\nEmail directive handled by <a href="https://app.mypraxos.com/log-in">My Praxos</a>'
            result = await gmail_integration.send_email(recipient, subject, singed_body)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="There was an error sending the email.")

    @tool
    async def get_emails_from_sender(sender_email: str, max_results: int = 10) -> ToolExecutionResponse:
        """Fetches the most recent emails from a specific sender in the user's Gmail account ({user_email})."""
        try:
            emails = await gmail_integration.get_emails_from_sender(sender_email, max_results)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"An error occurred while fetching emails from {sender_email}.")

    @tool
    async def find_contact_email(name: str) -> ToolExecutionResponse:
        """Searches the user's Google Contacts for a person's email address ({user_email}) by their name."""
        try:
            contacts = await gmail_integration.find_contact_email(name)
            if not contacts:
                logger.info(f"No contacts found matching the name '{name}'.")
                return ToolExecutionResponse(status="success", result=f"No contacts found matching the name '{name}'.")
            return ToolExecutionResponse(status="success", result=contacts)
        except Exception as e:
            logger.error(f"Error searching for contact '{name}': {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"An error occurred while searching for the contact '{name}'.")

    @tool
    async def search_gmail(query: str, max_results: int = 10) -> ToolExecutionResponse:
        """
        Searches for emails in the user's Gmail account ({user_email}) using a specific query.
        Can be used to find emails by sender, subject, keywords in the body, or a combination.
        Example queries: 'from:elon@musk.com subject:starship', 'dinner plans', 'is:unread'.
        """
        logger.info(f"Searching Gmail with query: '{query}'")
        try:
            emails = await gmail_integration.search_emails(query, max_results)
            response = ToolExecutionResponse(status="success", result=emails)
            logger.info(f"Gmail search response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error searching Gmail: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="An error occurred during the email search.")
        
    
    user_email = gmail_integration.get_user_email_address()
    send_email.description = send_email.description.format(user_email=user_email)
    get_emails_from_sender.description = get_emails_from_sender.description.format(user_email=user_email)
    find_contact_email.description = find_contact_email.description.format(user_email=user_email)
    search_gmail.description = search_gmail.description.format(user_email=user_email)
    
    return [send_email, get_emails_from_sender, find_contact_email, search_gmail]
