import json
from typing import Optional, List
from langchain_core.tools import tool
from src.integrations.gdrive.gdrive_client import GoogleDriveIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_drive_tools(gdrive_integration: GoogleDriveIntegration) -> List:
    """Creates all Google Drive related tools, dynamically configured for the user's accounts."""

    @tool
    async def search_google_drive_files(
        query: str, 
        max_results: Optional[int] = 20,
        account: Optional[str] = None  # 1. Add optional 'account' parameter
    ) -> ToolExecutionResponse:
        """
        Searches for files in the user's Google Drive using advanced query syntax.
        
        Args:
            query: Search query. Can include file names, content, or Google Drive search operators like:
                   - "name contains 'report'" (search by name)
                   - "fullText contains 'keyword'" (search file contents)
                   - "mimeType='application/vnd.google-apps.document'" (search by file type)
            max_results: Maximum number of results to return.
            account: The specific account to search in if the user has multiple.
        """
        try:
            # 2. Corrected method call and pass 'account'
            results = await gdrive_integration.list_files(query=query, max_results=max_results, account=account)
            return ToolExecutionResponse(status="success", result=results)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="An error occurred while searching Google Drive.")

    @tool
    async def save_file_to_drive(
        file_url: str, 
        file_name: str, 
        drive_folder_id: Optional[str] = None,
        account: Optional[str] = None  # 1. Add optional 'account' parameter
    ) -> ToolExecutionResponse:
        """Downloads a file from a URL and saves it to the user's Google Drive."""
        try:
            # 2. Pass 'account' to the integration method
            result = await gdrive_integration.save_file_to_drive(
                file_url, file_name, drive_folder_id=drive_folder_id, account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Could not save the file to Google Drive.")

    @tool
    async def create_text_file_in_drive(
        filename: str, 
        content: str, 
        drive_folder_id: Optional[str] = None,
        account: Optional[str] = None  # 1. Add optional 'account' parameter
    ) -> ToolExecutionResponse:
        """Creates a new text file with the given content in the user's Google Drive."""
        try:
            # 2. Pass 'account' to the integration method
            file_metadata = await gdrive_integration.create_text_file(
                filename, content, drive_folder_id=drive_folder_id, account=account
            )
            return ToolExecutionResponse(status="success", result=f"File '{filename}' created. Link: {file_metadata.get('webViewLink')}")
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Could not create the text file in Google Drive.")

    @tool
    async def read_file_content_by_id(
        file_id: str,
        account: Optional[str] = None  # 1. Add optional 'account' parameter
    ) -> ToolExecutionResponse:
        """Reads the content of a file from the user's Google Drive using its file ID."""
        try:
            # 2. Pass 'account' to the integration method
            content = await gdrive_integration.read_file_content_by_id(file_id, account=account)
            return ToolExecutionResponse(status="success", result=content)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"Could not read file with ID '{file_id}'.")

    # This tool is now functionally covered by search_google_drive_files, but we keep it
    # for simpler "browsing" use cases as its docstring is simpler for the AI.
    @tool
    async def list_drive_files(
        folder_id: Optional[str] = None,
        max_results: int = 50, 
        account: Optional[str] = None  # 1. Add optional 'account' parameter
    ) -> ToolExecutionResponse:
        """Lists files in the user's Google Drive, optionally within a specific folder."""
        try:
            # 2. Pass 'account' to the integration method
            files = await gdrive_integration.list_files(folder_id=folder_id, max_results=max_results, account=account)
            return ToolExecutionResponse(status="success", result=files)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Could not list files from Google Drive.")
    
    # 3. New logic to dynamically update descriptions for single vs. multiple accounts
    accounts = gdrive_integration.get_connected_accounts()
    if not accounts:
        return []

    all_tools = [
        search_google_drive_files, 
        save_file_to_drive, 
        create_text_file_in_drive, 
        read_file_content_by_id, 
        list_drive_files
    ]

    if len(accounts) == 1:
        user_email = accounts[0]
        for t in all_tools:
            t.description += f" The user's connected Google Drive account is {user_email}."
    else:
        account_list_str = ", ".join(f"'{acc}'" for acc in accounts)
        for t in all_tools:
            t.description += (
                f" The user has multiple accounts. You MUST use the 'account' parameter to specify which one to use. "
                f"Available accounts are: [{account_list_str}]."
            )

    return all_tools