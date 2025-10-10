from langchain_core.tools import tool
from src.integrations.dropbox.dropbox_client import DropboxIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from typing import Optional
import json

logger = setup_logger(__name__)

def create_dropbox_tools(dropbox_integration: DropboxIntegration) -> list:
    """Creates Dropbox related tools with multi-account support."""

    @tool
    async def list_dropbox_accounts() -> ToolExecutionResponse:
        """
        Lists all connected Dropbox accounts for the user.
        Use this first to see which Dropbox accounts are available.
        """
        try:
            accounts = dropbox_integration.get_connected_accounts()
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({"accounts": accounts})
            )
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def save_file_to_dropbox(file_path: str, content: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Saves a text content to a file in Dropbox.

        Args:
            file_path: Path where to save the file in Dropbox (e.g., "/Documents/notes.txt")
            content: Text content to save
            account: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
        """
        try:
            await dropbox_integration.save_file(file_path, content.encode('utf-8'), account=account)
            return ToolExecutionResponse(status="success", result=f"File '{file_path}' saved to Dropbox successfully.")
        except ValueError as e:
            # Multi-account error - let user know they need to specify account
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def read_file_from_dropbox(file_path: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Reads the content of a file from Dropbox.

        Args:
            file_path: Path to the file in Dropbox
            account: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
        """
        try:
            content = await dropbox_integration.read_file(file_path, account=account)
            return ToolExecutionResponse(status="success", result=content.decode('utf-8'))
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"Could not read the file '{file_path}' from Dropbox.")

    @tool
    async def list_dropbox_files(folder_path: str = "", recursive: bool = False, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Lists files and folders in a Dropbox directory.

        Args:
            folder_path: Path to the folder (empty string for root folder)
            recursive: If True, lists all files recursively in subfolders (default: False)
            account: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
        """
        try:
            files = await dropbox_integration.list_files(folder_path, recursive=recursive, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "files": files,
                    "count": len(files),
                    "folder": folder_path or "/"
                })
            )
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def search_dropbox_files(query: str, max_results: int = 100, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Searches for files in Dropbox by filename or content.
        This searches across the entire Dropbox account.

        Args:
            query: Search query (searches in filenames and file content)
            max_results: Maximum number of results to return (default: 100, max: 1000)
            account: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
        """
        try:
            results = await dropbox_integration.search_files(query, max_results=max_results, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "results": results,
                    "count": len(results),
                    "query": query
                })
            )
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    return [
        list_dropbox_accounts,
        save_file_to_dropbox,
        read_file_from_dropbox,
        list_dropbox_files,
        search_dropbox_files
    ]
