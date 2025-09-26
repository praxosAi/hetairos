import json
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from src.integrations.notion.notion_client import NotionIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_notion_tools(notion_client: NotionIntegration) -> List:
    """Create a comprehensive suite of Notion-related tools."""

    @tool
    async def list_notion_databases() -> ToolExecutionResponse:
        """
        Lists all databases that the agent has access to in Notion.
        This is useful for finding the 'database_id' for other tools.
        """
        try:
            databases = await notion_client.list_databases()
            return ToolExecutionResponse(status="success", result=json.dumps(databases))
        except Exception as e:
            logger.error(f"Error listing Notion databases: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def query_notion_database(database_id: str, filter: Dict = None, sorts: List[Dict] = None) -> ToolExecutionResponse:
        """
        Queries a specific Notion database with optional filters and sorts.
        This is the preferred way to find specific, structured information.
        Example filter: {"property": "Status", "select": {"equals": "In Progress"}}
        """
        try:
            results = await notion_client.query_database(database_id, filter, sorts)
            return ToolExecutionResponse(status="success", result=json.dumps(results))
        except Exception as e:
            logger.error(f"Error querying Notion database: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_notion_page_or_database_entry(
        title: str,
        content: List[Dict[str, Any]],
        parent_page_id: Optional[str] = None,
        database_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new page or a database entry in Notion.
        - To create a sub-page, provide 'parent_page_id'.
        - To create a database entry, provide 'database_id' and the 'properties' for the entry.
        Content Example: [{"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Text."}}]}}]
        Properties Example: {"Status": {"select": {"name": "Done"}}}
        """
        try:
            page = await notion_client.create_page(
                title=title,
                content=content,
                parent_page_id=parent_page_id,
                database_id=database_id,
                properties=properties
            )
            return ToolExecutionResponse(status="success", result={"page_link": page.get('url')})
        except Exception as e:
            logger.error(f"Error creating Notion page/entry: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def append_to_notion_page(page_id: str, content: List[Dict[str, Any]]) -> ToolExecutionResponse:
        """
        Appends content (blocks) to an existing Notion page.
        This is the primary way to add new information to a page.
        Content Example: [{"type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "New Section"}}]}}]
        """
        try:
            await notion_client.append_block_children(block_id=page_id, children=content)
            return ToolExecutionResponse(status="success", result=f"Content successfully appended to page {page_id}.")
        except Exception as e:
            logger.error(f"Error appending to Notion page: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def update_notion_page_properties(page_id: str, properties: Dict[str, Any]) -> ToolExecutionResponse:
        """
        Updates the properties of a Notion page, such as title or database fields.
        This is useful for changing the status of a task, renaming a page, etc.
        Properties Example: {"Status": {"select": {"name": "Archived"}}, "In Progress": {"checkbox": false}}
        """
        try:
            await notion_client.update_page_properties(page_id=page_id, properties=properties)
            return ToolExecutionResponse(status="success", result=f"Properties updated for page {page_id}.")
        except Exception as e:
            logger.error(f"Error updating Notion page properties: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_notion_page_content(page_id: str) -> ToolExecutionResponse:
        """
        Retrieves the content (blocks) of a Notion page.
        """
        try:
            content = await notion_client.get_page_content(page_id)
            return ToolExecutionResponse(status="success", result=json.dumps(content))
        except Exception as e:
            logger.error(f"Error getting Notion page content: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    return [
        list_notion_databases,
        query_notion_database,
        create_notion_page_or_database_entry,
        append_to_notion_page,
        update_notion_page_properties,
        get_notion_page_content,
    ]