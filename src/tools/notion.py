import json
from typing import List, Dict, Any
from langchain_core.tools import tool
from src.integrations.notion.notion_client import NotionIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_notion_tools(notion_client: NotionIntegration) -> List:
    """Create Notion-related tools"""

    @tool
    async def create_notion_page(
        parent_page_id: str,
        title: str,
        content: List[Dict[str, Any]]
    ) -> ToolExecutionResponse:
        """
        Creates a new page in Notion.

        Args:
            parent_page_id: The ID of the parent page.
            title: The title of the new page.
            content: The content of the page, as a list of block objects.
                     Example: [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "This is a paragraph."}}]}}]
        """
        try:
            page = await notion_client.create_page(parent_page_id, title, content)
            return ToolExecutionResponse(status="success", result={"page_link": page.get('url')})
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def search_notion_pages(query: str) -> str:
        """
        Searches for pages in Notion.

        Args:
            query: The search query.
        """
        try:
            results = await notion_client.search_pages(query)
            return json.dumps(results)
        except Exception as e:
            return f"Error searching Notion pages: {e}"

    @tool
    async def get_notion_page_content(page_id: str) -> str:
        """
        Retrieves the content of a Notion page.

        Args:
            page_id: The ID of the page to retrieve content from.
        """
        try:
            content = await notion_client.get_page_content(page_id)
            return json.dumps(content)
        except Exception as e:
            return f"Error getting Notion page content: {e}"

    return [create_notion_page, search_notion_pages, get_notion_page_content]
