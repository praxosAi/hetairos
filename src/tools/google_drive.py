from typing import Optional, List
from langchain_core.tools import tool
from src.integrations.gdrive.gdrive_client import GoogleDriveIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_drive_tools(gdrive_integration: GoogleDriveIntegration) -> List:
    """Creates all Google Drive related tools."""

    @tool
    async def save_file_to_drive(file_url: str, file_name: str, drive_folder_id: Optional[str] = None) -> ToolExecutionResponse:
        """Downloads a file from a URL and saves it to the user's Google Drive which is under {user_email} google account."""
        try:
            result = await gdrive_integration.save_file_to_drive(file_url, file_name, drive_folder_id)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_text_file_in_drive(filename: str, content: str, drive_folder_id: Optional[str] = None) -> ToolExecutionResponse:
        """Creates a new text file with the given content into the user's Google Drive ({user_email})."""
        try:
            file_metadata = await gdrive_integration.create_text_file(filename, content, drive_folder_id)
            return ToolExecutionResponse(status="success", result=f"File '{filename}' created successfully. View it here: {file_metadata.get('webViewLink')}")
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def read_file_content_by_id(file_id: str) -> ToolExecutionResponse:
        """Reads the content of a file from user's Google Drive ({user_email}) using its file ID. Use list_drive_files to get file IDs first."""
        try:
            content = await gdrive_integration.read_file_content_by_id(file_id)
            return ToolExecutionResponse(status="success", result=content)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"Could not read the file with ID '{file_id}'. Make sure the file exists and you have permission to read it.")

    @tool
    async def list_drive_files(query: Optional[str] = None, max_results: int = 50, folder_id: Optional[str] = None) -> ToolExecutionResponse:
        """Lists files in the user's Google Drive ({user_email}).
        - If query is None or empty: Lists all files in the drive
        - If query is provided: Searches for files whose names contain the query string
        - folder_id: Optional folder ID to limit search to a specific folder
        - max_results: Maximum number of files to return (default 50)
        """
        try:
            files = await gdrive_integration.list_files(query, max_results, folder_id)
            return ToolExecutionResponse(status="success", result=files)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Could not list files from Google Drive.")
    user_info = gdrive_integration.get_user_info()
    user_email = user_info.get('email', '')

    save_file_to_drive.description = save_file_to_drive.description.format(user_email=user_email)
    create_text_file_in_drive.description = create_text_file_in_drive.description.format(user_email=user_email)
    read_file_content_by_id.description = read_file_content_by_id.description.format(user_email=user_email)
    list_drive_files.description = list_drive_files.description.format(user_email=user_email)

    return [save_file_to_drive, create_text_file_in_drive, read_file_content_by_id, list_drive_files]