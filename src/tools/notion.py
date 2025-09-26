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
    async def list_workspace_content() -> ToolExecutionResponse:
        """
        Provides a high-level overview of the Notion workspace by listing all accessible databases and top-level pages.
        This should be the first tool used to understand the structure of the user's Notion workspace.
        """
        logger.info("Listing Notion workspace content...")
        try:
            # Fetch all databases
            databases = await notion_client.list_databases()
            
            # Fetch all pages that are NOT in a database
            standalone_pages_filter = {
                "and": [
                    {"property": "object", "value": "page"},
                    {"property": "parent", "database_id": {"is_empty": True}}
                ]
            }
            standalone_pages = await notion_client.search_pages(query="", custom_filter=standalone_pages_filter)
            
            result = {
                "databases": databases,
                "standalone_pages": standalone_pages
            }
            response = ToolExecutionResponse(status="success", result=json.dumps(result))
            logger.info(f"Notion workspace content response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error listing Notion workspace content: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def query_notion_database(database_id: str, filter: Dict = None, sorts: List[Dict] = None) -> ToolExecutionResponse:
        """
        Queries a specific Notion database to find pages matching certain criteria.
        This is the most reliable way to find pages when you know which database they are in.
        """
        logger.info(f"Querying Notion database: {database_id} with filter: {filter}")
        try:
            results = await notion_client.query_database(database_id, filter, sorts)
            response = ToolExecutionResponse(status="success", result=json.dumps(results))
            logger.info(f"Notion database query response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error querying Notion database: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def search_notion_pages_by_keyword(query: str) -> ToolExecutionResponse:
        """
        Performs a global keyword search across all pages. Use this to find a specific page by its title
        when you don't know where it is located.
        """
        logger.info(f"Searching Notion pages by keyword: {query}")
        try:
            results = await notion_client.search_pages(query)
            response = ToolExecutionResponse(status="success", result=json.dumps(results))
            logger.info(f"Notion keyword search response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error searching Notion pages by keyword: {e}", exc_info=True)
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
        """
        logger.info(f"Creating Notion page/entry with title: {title}")
        try:
            page = await notion_client.create_page(
                title=title, content=content, parent_page_id=parent_page_id,
                database_id=database_id, properties=properties
            )
            response = ToolExecutionResponse(status="success", result={"page_link": page.get('url')})
            logger.info(f"Create Notion page/entry response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error creating Notion page/entry: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def append_to_notion_page(page_id: str, content: List[Dict[str, Any]]) -> ToolExecutionResponse:
        """
        Appends content (blocks) to an existing Notion page.
        """
        logger.info(f"Appending content to Notion page: {page_id}")
        try:
            await notion_client.append_block_children(block_id=page_id, children=content)
            response = ToolExecutionResponse(status="success", result=f"Content successfully appended to page {page_id}.")
            logger.info(f"Append to Notion page response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error appending to Notion page: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def update_notion_page_properties(page_id: str, properties: Dict[str, Any]) -> ToolExecutionResponse:
        """
        Updates the properties of a Notion page, such as title or database fields.
        """
        logger.info(f"Updating properties for Notion page: {page_id}")
        try:
            await notion_client.update_page_properties(page_id=page_id, properties=properties)
            response = ToolExecutionResponse(status="success", result=f"Properties updated for page {page_id}.")
            logger.info(f"Update Notion page properties response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error updating Notion page properties: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_notion_page_content(page_id: str) -> ToolExecutionResponse:
        """
        Retrieves the content (blocks) of a Notion page.
        """
        logger.info(f"Getting content for Notion page: {page_id}")
        try:
            content = await notion_client.get_page_content(page_id)
            response = ToolExecutionResponse(status="success", result=json.dumps(content))
            logger.info(f"Get Notion page content response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error getting Notion page content: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    return [
        list_workspace_content,
        query_notion_database,
        search_notion_pages_by_keyword,
        create_notion_page_or_database_entry,
        append_to_notion_page,
        update_notion_page_properties,
        get_notion_page_content,
    ]
