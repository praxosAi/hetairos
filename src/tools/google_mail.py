from typing import List
from langchain_core.tools import tool
from src.integrations.email.gmail_client import GmailIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from typing import Optional

logger = setup_logger(__name__)
def create_gmail_tools(gmail_integration: GmailIntegration) -> List:
    """Creates Gmail and Google Contacts related tools based on the user's connected accounts."""

    # 1. Add an optional 'from_account' parameter to the tool signature.
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
            # 2. Pass the 'from_account' parameter to the integration method.
            result = await gmail_integration.send_email(recipient, subject, signed_body, from_account=from_account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="There was an error sending the email.")


    @tool
    async def get_emails_from_sender(
        sender_email: str, 
        max_results: int = 10,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Fetches the most recent emails from a specific sender in the user's Gmail account."""
        try:
            # 2. Pass the 'account' parameter.
            emails = await gmail_integration.get_emails_from_sender(sender_email, max_results=max_results, account=account)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"An error occurred while fetching emails from {sender_email}.")

    # 1. Add an optional 'account' parameter.
    @tool
    async def find_contact_email(
        name: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """Searches the user's Google Contacts for a person's email address by their name."""
        try:
            # 2. Pass the 'account' parameter.
            contacts = await gmail_integration.find_contact_email(name, account=account)
            if not contacts:
                return ToolExecutionResponse(status="success", result=f"No contacts found matching '{name}'.")
            return ToolExecutionResponse(status="success", result=contacts)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"An error occurred while searching for '{name}'.")

    # 1. Add an optional 'account' parameter.
    @tool
    async def search_gmail(
        query: str, 
        max_results: int = 10,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Searches for emails in the user's Gmail account using a specific query.
        Can be used to find emails by sender, subject, keywords, or a combination.
        Example queries: 'from:elon@musk.com subject:starship', 'dinner plans', 'is:unread'.
        """
        try:
            # 2. Pass the 'account' parameter.
            emails = await gmail_integration.search_emails(query, max_results=max_results, account=account)
            return ToolExecutionResponse(status="success", result=emails)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="An error occurred during the email search.")
    
    # 3. Dynamically update tool descriptions based on the number of connected accounts.
    accounts = gmail_integration.get_connected_accounts()
    if not accounts:
        return [] # Return no tools if no accounts are authenticated.

    all_tools = [send_email, get_emails_from_sender, find_contact_email, search_gmail]

    if len(accounts) == 1:
        # If there's only one account, mention it in the description.
        user_email = accounts[0]
        for t in all_tools:
            t.description += f" The user's connected account is {user_email}."
    else:
        # If there are multiple, instruct the AI to use the 'account' parameter.
        account_list_str = ", ".join(f"'{acc}'" for acc in accounts)
        for t in all_tools:
            param = "'from_account'" if t.name == "send_email" else "'account'"
            t.description += (
                f" The user has multiple accounts. You MUST use the {param} parameter to specify which one to use. "
                f"Available accounts are: [{account_list_str}]."
            )
            
    return all_tools
