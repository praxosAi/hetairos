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
    async def list_databases() -> ToolExecutionResponse:
        """
        Provides a high-level overview of the Notion workspace by listing all accessible databases and top-level pages.
        This should be the first tool used to understand the structure of the user's Notion workspace.
        """
        logger.info("Listing Notion databases...")
        try:
            # Fetch all databases
            databases = await notion_client.list_databases()

            result = {
                "databases": databases,
            }
            response = ToolExecutionResponse(status="success", result=json.dumps(result))
            logger.info(f"Notion workspace content response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error listing Notion workspace content: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def list_notion_pages() -> List[Dict[str, Any]]:
        """
        Lists all top-level pages in the Notion workspace.
        """
        logger.info("Listing Notion top-level pages...")
        try:
            pages = await notion_client.search_pages(query="")
            response = ToolExecutionResponse(status="success", result=json.dumps(pages))
            return response
        except Exception as e:
            logger.error(f"Error listing Notion top-level pages: {e}", exc_info=True)
            return []
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
    async def get_all_workspace_entries() -> ToolExecutionResponse:
        """
        Retrieves all pages and databases in the Notion workspace.
        This is a more exhaustive search and should be used when you need to find something but don't know where it is.
        """
        logger.info("Retrieving all Notion workspace entries...")
        try:
            results = await notion_client.get_all_workspace_entries()
            response = ToolExecutionResponse(status="success", result=json.dumps(results))
            logger.info(f"All Notion workspace entries response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error retrieving all Notion workspace entries: {e}", exc_info=True)
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
    async def create_notion_page(
        title: str,
        content: List[Dict[str, Any]],
        parent_page_id: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new page in Notion.
        - To create a sub-page, provide 'parent_page_id'.
        - If 'parent_page_id' is not provided, the page will be created at the workspace root.
        """
        logger.info(f"Creating Notion page with title: {title}")
        try:
            page = await notion_client.create_page(
                title=title, content=content, parent_page_id=parent_page_id
            )
            response = ToolExecutionResponse(status="success", result={"page_link": page.get('url')})
            logger.info(f"Create Notion page response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error creating Notion page: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_notion_database_entry(
        database_id: str,
        title: str,
        content: List[Dict[str, Any]],
        properties: Optional[Dict[str, Any]] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new entry in a Notion database.
        - 'database_id' is required to specify the target database.
        - 'properties' should be provided to populate the database entry's fields.
        """
        logger.info(f"Creating Notion database entry with title: {title}")
        try:
            page = await notion_client.create_page(
                title=title, content=content, database_id=database_id, properties=properties
            )
            response = ToolExecutionResponse(status="success", result={"page_link": page.get('url')})
            logger.info(f"Create Notion database entry response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error creating Notion database entry: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_notion_database(
        parent_page_id: str,
        title: str,
        properties: Dict[str, Any]
    ) -> ToolExecutionResponse:
        """
        Creates a new database in Notion.
        - 'parent_page_id' is required to specify where the database should be created.
        - 'title' is the title of the new database.
        - 'properties' defines the schema of the database.
        """
        logger.info(f"Creating Notion database with title: {title}")
        try:
            database = await notion_client.create_database(
                parent_page_id=parent_page_id, title=title, properties=properties
            )
            response = ToolExecutionResponse(status="success", result={"database_link": database.get('url')})
            logger.info(f"Create Notion database response: {response.result}")
            return response
        except Exception as e:
            logger.error(f"Error creating Notion database: {e}", exc_info=True)
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
        list_databases,
        list_notion_pages,
        query_notion_database,
        search_notion_pages_by_keyword,
        create_notion_page,
        create_notion_database_entry,
        create_notion_database,
        append_to_notion_page,
        update_notion_page_properties,
        get_notion_page_content,
        get_all_workspace_entries,
    ]
