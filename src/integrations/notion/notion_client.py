import aiohttp
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

class NotionIntegration(BaseIntegration):
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.api_key = None
        self.base_url = "https://api.notion.com/v1"
        self.headers = {}

    async def authenticate(self) -> bool:
        """Fetches the Notion API key from the database."""
        token_info = await integration_service.get_integration_token(self.user_id, 'notion')
        if not token_info or 'access_token' not in token_info:
            logger.error(f"Failed to retrieve Notion API key for user {self.user_id}")
            return False
        
        self.api_key = token_info['access_token']
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        return True

    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """
        Fetches pages that have been recently edited in Notion.
        """
        if not self.api_key:
            logger.error("Notion client not authenticated.")
            return []

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        url = f"{self.base_url}/search"
        data = {
            "filter": {
                "property": "last_edited_time",
                "timestamp": {
                    "after": since.isoformat()
                }
            },
            "sort": {
                "direction": "descending",
                "timestamp": "last_edited_time"
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    search_results = await response.json()
                    
                    # Fetch content for each page
                    pages = []
                    for result in search_results.get("results", []):
                        if result.get("object") == "page":
                            page_content_blocks = await self.get_page_content(result["id"])
                            page_text_content = self._convert_blocks_to_text(page_content_blocks)
                            
                            title = "Untitled"
                            if result.get("properties", {}).get("title", {}).get("title"):
                                title = result["properties"]["title"]["title"][0].get("plain_text", "Untitled")

                            pages.append({
                                "id": result["id"],
                                "title": title,
                                "url": result.get("url"),
                                "last_edited_time": result.get("last_edited_time"),
                                "content": page_text_content, # For potential future use
                                "raw_blocks": page_content_blocks 
                            })
                    return pages
            except aiohttp.ClientError as e:
                logger.error(f"Error searching Notion pages: {e}")
                return []

    def _convert_blocks_to_text(self, blocks: List[Dict]) -> str:
        """Converts a list of Notion blocks to a single string of plain text."""
        text_parts = []
        for block in blocks:
            block_type = block.get("type")
            if block_type and block.get(block_type, {}).get("rich_text"):
                for text_item in block[block_type]["rich_text"]:
                    text_parts.append(text_item.get("plain_text", ""))
            if block.get("has_children"):
                # Recursively process child blocks, adding indentation
                child_text = self._convert_blocks_to_text(block.get("children", []))
                for line in child_text.split('\n'):
                    if line: # Avoid indenting empty lines
                        text_parts.append(f"\t{line}")

        return "\n".join(text_parts)

    async def get_page_content(self, page_id: str) -> List[Dict[str, Any]]:
        """Retrieves the content of a Notion page, including nested blocks."""
        return await self._get_all_blocks(page_id)

    async def _get_block_children(self, block_id: str) -> List[Dict[str, Any]]:
        """Retrieves the children of a specific block."""
        url = f"{self.base_url}/blocks/{block_id}/children"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    return (await response.json()).get("results", [])
            except aiohttp.ClientError as e:
                logger.error(f"Error getting block children: {e}")
                raise

    async def _get_all_blocks(self, block_id: str) -> List[Dict[str, Any]]:
        """Recursively retrieves all blocks and their children."""
        blocks = await self._get_block_children(block_id)
        for block in blocks:
            if block.get("has_children"):
                block["children"] = await self._get_all_blocks(block["id"])
        return blocks

    async def search_pages(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches for pages in Notion using a text query.

        Args:
            query: The search query string.

        Returns:
            A list of page objects matching the search query.
        """
        if not self.api_key:
            raise Exception("Notion client not authenticated.")

        url = f"{self.base_url}/search"
        data = {
            "query": query,
            "filter": {
                "value": "page",
                "property": "object"
            },
            "sort": {
                "direction": "descending",
                "timestamp": "last_edited_time"
            }
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    search_results = await response.json()
                    
                    pages = []
                    for result in search_results.get("results", []):
                        if result.get("object") == "page":
                            title = "Untitled"
                            if result.get("properties", {}).get("title", {}).get("title"):
                                title = result["properties"]["title"]["title"][0].get("plain_text", "Untitled")
                            
                            pages.append({
                                "id": result["id"],
                                "title": title,
                                "url": result.get("url"),
                                "last_edited_time": result.get("last_edited_time"),
                                "created_time": result.get("created_time")
                            })
                    
                    return pages
            except aiohttp.ClientError as e:
                logger.error(f"Error searching Notion pages: {e}")
                raise

    async def create_page(
        self, 
        title: str, 
        content: List[Dict[str, Any]], 
        parent_page_id: str = None, 
        database_id: str = None,
        properties: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Creates a new page in Notion, either as a sub-page or in a database.
        """
        if not self.api_key:
            raise Exception("Notion client not authenticated.")
        if not parent_page_id and not database_id:
            raise ValueError("Either parent_page_id or database_id must be provided.")

        url = f"{self.base_url}/pages"
        
        # Determine the parent
        parent_data = {}
        if database_id:
            parent_data = {"database_id": database_id}
        else:
            parent_data = {"page_id": parent_page_id}

        # Setup properties, ensuring the title is correctly formatted
        page_properties = properties or {}
        page_properties["title"] = {
            "title": [{"text": {"content": title}}]
        }

        data = {
            "parent": parent_data,
            "properties": page_properties,
            "children": content,
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                logger.error(f"Error creating Notion page: {e}")
                raise

    async def list_databases(self) -> List[Dict[str, Any]]:
        """Lists all databases accessible to the integration."""
        if not self.api_key:
            raise Exception("Notion client not authenticated.")

        url = f"{self.base_url}/search"
        data = {
            "filter": {
                "value": "database",
                "property": "object"
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    results = await response.json()
                    
                    databases = []
                    for db in results.get("results", []):
                        title = "Untitled Database"
                        if db.get("title"):
                            title = db["title"][0].get("plain_text", title)
                        
                        databases.append({
                            "id": db["id"],
                            "title": title,
                            "url": db.get("url")
                        })
                    return databases
            except aiohttp.ClientError as e:
                logger.error(f"Error listing Notion databases: {e}")
                raise

    async def query_database(self, database_id: str, filter: Dict = None, sorts: List[Dict] = None) -> List[Dict[str, Any]]:
        """
        Queries a Notion database with optional filters and sorts.
        """
        if not self.api_key:
            raise Exception("Notion client not authenticated.")

        url = f"{self.base_url}/databases/{database_id}/query"
        data = {}
        if filter:
            data["filter"] = filter
        if sorts:
            data["sorts"] = sorts

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    results = await response.json()
                    
                    # Simplified parsing of results
                    pages = []
                    for page in results.get("results", []):
                        title = "Untitled"
                        # Check for the 'title' property, which might have a different name in some databases
                        for prop_name, prop_value in page.get("properties", {}).items():
                            if prop_value.get("type") == "title":
                                if prop_value["title"]:
                                    title = prop_value["title"][0].get("plain_text", "Untitled")
                                break
                        
                        pages.append({
                            "id": page["id"],
                            "title": title,
                            "url": page.get("url"),
                            "properties": page.get("properties") # Include all properties
                        })
                    return pages
            except aiohttp.ClientError as e:
                logger.error(f"Error querying Notion database {database_id}: {e}")
                raise

    async def append_block_children(self, block_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Appends a list of blocks to a given block (page or other).
        """
        if not self.api_key:
            raise Exception("Notion client not authenticated.")

        url = f"{self.base_url}/blocks/{block_id}/children"
        data = {"children": children}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.patch(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                logger.error(f"Error appending blocks to {block_id}: {e}")
                raise

    async def update_page_properties(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates the properties of a Notion page.
        """
        if not self.api_key:
            raise Exception("Notion client not authenticated.")

        url = f"{self.base_url}/pages/{page_id}"
        data = {"properties": properties}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.patch(url, headers=self.headers, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                logger.error(f"Error updating page properties for {page_id}: {e}")
                raise