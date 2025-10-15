import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from notion_client import AsyncClient
from datetime import datetime, timedelta
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

class NotionIntegration(BaseIntegration):
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.clients: Dict[str, AsyncClient] = {}
        self.connected_accounts: List[str] = []

    async def authenticate(self) -> bool:
        """
        Authenticates all connected Notion workspaces for the user.
        Each workspace gets its own AsyncClient instance.
        """
        logger.info(f"Authenticating all Notion workspaces for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(
            self.user_id, 'notion'
        )

        if not integration_records:
            logger.warning(f"No Notion integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record
        ]

        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict) -> bool:
        """Authenticates a single Notion workspace and stores its client."""
        workspace_name = integration_record.get('connected_account')  # Workspace name or identifier
        integration_id = integration_record.get('_id')

        try:
            token_info = await integration_service.get_integration_token(
                self.user_id, 'notion', integration_id=integration_id
            )

            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve token for Notion workspace {workspace_name}")
                return False

            # Create Notion client for this workspace
            client = AsyncClient(auth=token_info['access_token'])

            # Store client and workspace
            self.clients[workspace_name] = client
            if workspace_name not in self.connected_accounts:
                self.connected_accounts.append(workspace_name)

            logger.info(f"Successfully authenticated Notion workspace {workspace_name}")
            return True

        except Exception as e:
            logger.error(f"Notion authentication failed for workspace {workspace_name}: {e}")
            return False

    def get_connected_accounts(self) -> List[str]:
        """Returns a list of successfully authenticated Notion workspaces."""
        return self.connected_accounts

    def _get_client_for_account(self, account: Optional[str] = None) -> Tuple[AsyncClient, str]:
        """
        Retrieves the Notion client and resolved workspace identifier.
        Handles default logic for single-workspace users.
        """
        if account:
            client = self.clients.get(account)
            if not client:
                raise ValueError(
                    f"Workspace '{account}' is not authenticated. "
                    f"Available workspaces: {self.connected_accounts}"
                )
            return client, account

        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.clients[default_account], default_account

        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Notion workspaces found for this user.")

        raise ValueError(
            f"Multiple Notion workspaces exist. Specify which workspace to use with "
            f"the 'account' parameter. Available workspaces: {self.connected_accounts}"
        )

    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetches pages that have been recently edited in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        logger.info(f"Fetching recent pages for Notion workspace {resolved_account} since {since}")

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

        response = await client.search(**search_params)

        pages = []
        for result in response.get("results", []):
            if result.get("object") == "page":
                page_content_blocks = await self.get_page_content(result["id"], account=resolved_account)
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
                    "raw_blocks": page_content_blocks,
                    "workspace": resolved_account
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

    async def list_databases(self, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all databases accessible in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)

        response = await client.search(filter={"property": "object", "value": "database"})
        databases = []
        for db in response.get("results", []):
            title = "Untitled Database"
            title_list = db.get("title", [])
            if title_list:
                title = title_list[0].get("plain_text", title)
            databases.append({
                "id": db["id"],
                "title": title,
                "url": db.get("url"),
                "workspace": resolved_account
            })
        return databases

    async def get_all_workspace_entries(self, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches all top-level pages and databases in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)

        entries = []
        start_cursor = None
        while True:
            response = await client.search(start_cursor=start_cursor)
            entries.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
        return entries

    async def search_pages(self, query: str = "", custom_filter: Optional[Dict[str, Any]] = None, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches for pages in a specific Notion workspace, optionally with a custom filter."""
        client, resolved_account = self._get_client_for_account(account)

        search_params = {"query": query}
        if custom_filter:
            search_params["filter"] = custom_filter
        else:
            search_params["filter"] = {"property": "object", "value": "page"}

        response = await client.search(**search_params)
        return response.get("results", [])

    async def query_database(self, database_id: str, filter: Dict = None, sorts: List[Dict] = None, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries a Notion database in a specific workspace."""
        client, resolved_account = self._get_client_for_account(account)

        query_params = {}
        if filter:
            query_params["filter"] = filter
        if sorts:
            query_params["sorts"] = sorts

        response = await client.databases.query(database_id=database_id, **query_params)
        return response.get("results", [])

    async def create_database(self, parent_page_id: str, title: str, properties: Dict[str, Any], *, account: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new database in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)

        parent = {"page_id": parent_page_id}
        title = [{"type": "text", "text": {"content": title}}]

        return await client.databases.create(
            parent=parent,
            title=title,
            properties=properties
        )

    async def create_page(self, title: str, content: List[Dict[str, Any]], parent_page_id: str = None, database_id: str = None, properties: Dict[str, Any] = None, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new page or database entry in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)

        if database_id:
            parent = {"database_id": database_id}
        elif parent_page_id:
            parent = {"page_id": parent_page_id}
        else:
            # workspace is the root.
            parent = {'type': 'workspace', 'workspace': True}

        page_properties = properties or {}

        # Ensure title is correctly formatted
        if "title" not in page_properties:
            page_properties["title"] = {"title": [{"text": {"content": title}}]}

        # Fix for date property validation
        for prop, value in page_properties.items():
            if isinstance(value, dict) and value.get("type") == "date" and "date" in value and "start" not in value["date"]:
                # Assuming if a date is provided, it's meant to be the start date
                # The Notion API requires a start date for date properties.
                # This is a minimal fix; a more robust solution might involve more complex logic
                # to determine start and end dates based on input.
                if isinstance(value["date"], str): # Handle case where date is just a string
                    page_properties[prop]["date"] = {"start": value["date"]}

        return await client.pages.create(
            parent=parent,
            properties=page_properties,
            children=content
        )

    async def append_block_children(self, block_id: str, children: List[Dict[str, Any]], *, account: Optional[str] = None) -> Dict[str, Any]:
        """Appends blocks to a page or another block in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)
        return await client.blocks.children.append(block_id=block_id, children=children)

    async def update_page_properties(self, page_id: str, properties: Dict[str, Any], *, account: Optional[str] = None) -> Dict[str, Any]:
        """Updates the properties of a page in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)
        return await client.pages.update(page_id=page_id, properties=properties)

    async def get_page_content(self, page_id: str, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all blocks from a page in a specific Notion workspace."""
        client, resolved_account = self._get_client_for_account(account)

        all_blocks = []
        start_cursor = None
        while True:
            response = await client.blocks.children.list(block_id=page_id, start_cursor=start_cursor)
            all_blocks.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
        return all_blocks
