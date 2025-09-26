import logging
from typing import List, Dict, Any, Optional
from notion_client import AsyncClient
from datetime import datetime, timedelta
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

class NotionIntegration(BaseIntegration):
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.notion_client: Optional[AsyncClient] = None

    async def authenticate(self) -> bool:
        """Fetches the Notion API key and initializes the AsyncClient."""
        token_info = await integration_service.get_integration_token(self.user_id, 'notion')
        if not token_info or 'access_token' not in token_info:
            logger.error(f"Failed to retrieve Notion API key for user {self.user_id}")
            return False
        
        self.notion_client = AsyncClient(auth=token_info['access_token'])
        return True

    async def fetch_recent_data(self) -> List[Dict]:
        """Fetches pages that have been recently edited in Notion."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        search_params = {
            "filter": {
                "property": "last_edited_time",
                "timestamp": {"after": since.isoformat()}
            },
            "sort": {
                "direction": "descending",
                "timestamp": "last_edited_time"
            }
        }
        
        response = await self.notion_client.search(**search_params)
        
        pages = []
        for result in response.get("results", []):
            if result.get("object") == "page":
                page_content_blocks = await self.get_page_content(result["id"])
                page_text_content = self._convert_blocks_to_text(page_content_blocks)
                
                title = "Untitled"
                # Find the title property, which is not always named 'title'
                for prop_name, prop_value in result.get("properties", {}).items():
                    if prop_value.get("type") == "title" and prop_value.get("title"):
                        title = prop_value["title"][0].get("plain_text", "Untitled")
                        break

                pages.append({
                    "id": result["id"],
                    "title": title,
                    "url": result.get("url"),
                    "last_edited_time": result.get("last_edited_time"),
                    "content": page_text_content,
                    "raw_blocks": page_content_blocks 
                })
        return pages

    def _convert_blocks_to_text(self, blocks: List[Dict]) -> str:
        """Converts a list of Notion blocks to a single string of plain text."""
        text_parts = []
        for block in blocks:
            block_type = block.get("type")
            if block_type and block.get(block_type, {}).get("rich_text"):
                for text_item in block[block_type]["rich_text"]:
                    text_parts.append(text_item.get("plain_text", ""))
        return "\n".join(text_parts)

    async def list_databases(self) -> List[Dict[str, Any]]:
        """Lists all databases accessible to the integration."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        
        response = await self.notion_client.search(filter={"property": "object", "value": "database"})
        databases = []
        for db in response.get("results", []):
            title = "Untitled Database"
            title_list = db.get("title", [])
            if title_list:
                title = title_list[0].get("plain_text", title)
            databases.append({"id": db["id"], "title": title, "url": db.get("url")})
        return databases
    async def get_all_workspace_entries(self) -> List[Dict[str, Any]]:
        """Fetches all top-level pages and databases in the Notion workspace."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        
        entries = []
        start_cursor = None
        while True:
            response = await self.notion_client.search(start_cursor=start_cursor)
            entries.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
        return entries
    async def search_pages(self, query: str = "", custom_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Searches for pages, optionally with a custom filter."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        
        search_params = {"query": query}
        if custom_filter:
            search_params["filter"] = custom_filter
        else:
            search_params["filter"] = {"property": "object", "value": "page"}
            
        response = await self.notion_client.search(**search_params)
        return response.get("results", [])

    async def query_database(self, database_id: str, filter: Dict = None, sorts: List[Dict] = None) -> List[Dict[str, Any]]:
        """Queries a Notion database."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        
        query_params = {}
        if filter:
            query_params["filter"] = filter
        if sorts:
            query_params["sorts"] = sorts
            
        response = await self.notion_client.databases.query(database_id=database_id, **query_params)
        return response.get("results", [])

    async def create_page(self, title: str, content: List[Dict[str, Any]], parent_page_id: str = None, database_id: str = None, properties: Dict[str, Any] = None) -> Dict[str, Any]:
        """Creates a new page or database entry."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        # if not parent_page_id and not database_id:
        #     raise ValueError("Either parent_page_id or database_id must be provided.")
        if database_id:
            parent = {"database_id": database_id}
        elif parent_page_id:
            parent = {"page_id": parent_page_id}
        else:
            ## workspace is the root.
            parent = {'type':'workspace','workspace':True}
        page_properties = properties or {}
        page_properties["title"] = {"title": [{"text": {"content": title}}]}

        return await self.notion_client.pages.create(
            parent=parent,
            properties=page_properties,
            children=content
        )

    async def append_block_children(self, block_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Appends blocks to a page or another block."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        return await self.notion_client.blocks.children.append(block_id=block_id, children=children)

    async def update_page_properties(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Updates the properties of a page."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        return await self.notion_client.pages.update(page_id=page_id, properties=properties)

    async def get_page_content(self, page_id: str) -> List[Dict[str, Any]]:
        """Retrieves all blocks from a page."""
        if not self.notion_client:
            raise Exception("Notion client not authenticated.")
        
        all_blocks = []
        start_cursor = None
        while True:
            response = await self.notion_client.blocks.children.list(block_id=page_id, start_cursor=start_cursor)
            all_blocks.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
        return all_blocks
