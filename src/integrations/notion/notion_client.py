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

    async def create_page(self, parent_page_id: str, title: str, content: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Creates a new page in Notion.

        Args:
            parent_page_id: The ID of the parent page.
            title: The title of the new page.
            content: The content of the page, as a list of block objects.
        """
        if not self.api_key:
            raise Exception("Notion client not authenticated.")

        url = f"{self.base_url}/pages"
        data = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {
                    "title": [
                        {
                            "text": {
                                "content": title,
                            },
                        },
                    ],
                },
            },
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