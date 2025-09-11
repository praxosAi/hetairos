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
    async def read_file_from_drive(file_name: str) -> ToolExecutionResponse:
        """Reads the content of a text file from user's Google Drive ({user_email}) by its name."""
        try:
            content = await gdrive_integration.read_file_from_drive(file_name)
            return ToolExecutionResponse(status="success", result=content)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"Could not read the file '{file_name}'. Make sure it exists and is a text file.")
    user_info = gdrive_integration.get_user_info()
    user_email = user_info.get('email', '')

    save_file_to_drive.description = save_file_to_drive.description.format(user_email=user_email)
    create_text_file_in_drive.description = create_text_file_in_drive.description.format(user_email=user_email)
    read_file_from_drive.description = read_file_from_drive.description.format(user_email=user_email)

    return [save_file_to_drive, create_text_file_in_drive, read_file_from_drive]