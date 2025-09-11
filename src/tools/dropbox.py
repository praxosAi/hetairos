from langchain_core.tools import tool
from src.integrations.dropbox.dropbox_client import DropboxIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_dropbox_tools(dropbox_integration: DropboxIntegration) -> list:
    """Creates Dropbox related tools."""

    @tool
    async def save_file_to_dropbox(file_path: str, content: str) -> ToolExecutionResponse:
        """Saves a text content to a file in Dropbox."""
        try:
            await dropbox_integration.save_file(file_path, content.encode('utf-8'))
            return ToolExecutionResponse(status="success", result=f"File '{file_path}' saved to Dropbox successfully.")
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def read_file_from_dropbox(file_path: str) -> ToolExecutionResponse:
        """Reads the content of a file from Dropbox."""
        try:
            content = await dropbox_integration.read_file(file_path)
            return ToolExecutionResponse(status="success", result=content.decode('utf-8'))
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"Could not read the file '{file_path}' from Dropbox.")

    return [save_file_to_dropbox, read_file_from_dropbox]
