import dropbox
import asyncio
from typing import Optional, Dict, List, Tuple
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from datetime import datetime, timedelta

logger = setup_logger(__name__)

class DropboxIntegration(BaseIntegration):

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.clients: Dict[str, dropbox.Dropbox] = {}
        self.connected_accounts: List[str] = []

    async def authenticate(self) -> bool:
        """
        Authenticates all connected Dropbox accounts for the user.
        Each account gets its own Dropbox client instance.
        """
        logger.info(f"Authenticating all Dropbox accounts for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(
            self.user_id, 'dropbox'
        )

        if not integration_records:
            logger.warning(f"No Dropbox integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record
        ]

        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict) -> bool:
        """Authenticates a single Dropbox account and stores its client."""
        account_id = integration_record.get('connected_account')  # Email or account identifier
        integration_id = integration_record.get('_id')

        try:
            token_info = await integration_service.get_integration_token(
                self.user_id, 'dropbox', integration_id=integration_id
            )

            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve token for Dropbox account {account_id}")
                return False

            # Create Dropbox client for this account
            client = dropbox.Dropbox(token_info['access_token'])

            # Store client and account
            self.clients[account_id] = client
            if account_id not in self.connected_accounts:
                self.connected_accounts.append(account_id)

            logger.info(f"Successfully authenticated Dropbox account {account_id}")
            return True

        except Exception as e:
            logger.error(f"Dropbox authentication failed for account {account_id}: {e}")
            return False

    def get_connected_accounts(self) -> List[str]:
        """Returns a list of successfully authenticated Dropbox accounts."""
        return self.connected_accounts

    def _get_client_for_account(self, account: Optional[str] = None) -> Tuple[dropbox.Dropbox, str]:
        """
        Retrieves the Dropbox client and resolved account identifier.
        Handles default logic for single-account users.
        """
        if account:
            client = self.clients.get(account)
            if not client:
                raise ValueError(
                    f"Account '{account}' is not authenticated. "
                    f"Available accounts: {self.connected_accounts}"
                )
            return client, account

        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.clients[default_account], default_account

        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Dropbox accounts found for this user.")

        raise ValueError(
            f"Multiple Dropbox accounts exist. Specify which account to use with "
            f"the 'account' parameter. Available accounts: {self.connected_accounts}"
        )

    async def save_file(self, file_path: str, content: bytes, *, account: Optional[str] = None):
        """Saves a file to Dropbox for a specific account."""
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Uploading file to Dropbox account {resolved_account}: {file_path}")
        client.files_upload(content, file_path, mode=dropbox.files.WriteMode.overwrite)

    async def read_file(self, file_path: str, *, account: Optional[str] = None) -> bytes:
        """Reads a file from Dropbox for a specific account."""
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Reading file from Dropbox account {resolved_account}: {file_path}")
        _, res = client.files_download(path=file_path)
        return res.content

    async def list_files(self, folder_path: str = "", *, recursive: bool = False, account: Optional[str] = None) -> List[Dict]:
        """Lists files in a Dropbox folder for a specific account."""
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Listing files in Dropbox account {resolved_account}: {folder_path or '/'} (recursive={recursive})")

        try:
            result = client.files_list_folder(folder_path, recursive=recursive)
            files = []

            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    files.append({
                        'name': entry.name,
                        'path': entry.path_display,
                        'size': entry.size,
                        'modified': entry.client_modified.isoformat() if entry.client_modified else None,
                        'id': entry.id,
                        'type': 'file'
                    })
                elif isinstance(entry, dropbox.files.FolderMetadata):
                    files.append({
                        'name': entry.name,
                        'path': entry.path_display,
                        'id': entry.id,
                        'type': 'folder'
                    })

            return files
        except dropbox.exceptions.ApiError as e:
            logger.error(f"Error listing files for account {resolved_account}: {e}")
            return []

    async def search_files(self, query: str, *, max_results: int = 100, account: Optional[str] = None) -> List[Dict]:
        """Searches for files in Dropbox by filename or content."""
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Searching Dropbox account {resolved_account} for: {query}")

        try:
            # Use search_v2 for better results
            search_result = client.files_search_v2(
                query=query,
                options=dropbox.files.SearchOptions(
                    max_results=max_results,
                    file_status=dropbox.files.FileStatus.active,
                    filename_only=False  # Search in content too
                )
            )

            files = []
            for match in search_result.matches:
                metadata = match.metadata.get_metadata()
                if isinstance(metadata, dropbox.files.FileMetadata):
                    files.append({
                        'name': metadata.name,
                        'path': metadata.path_display,
                        'size': metadata.size,
                        'modified': metadata.client_modified.isoformat() if metadata.client_modified else None,
                        'id': metadata.id,
                        'type': 'file'
                    })
                elif isinstance(metadata, dropbox.files.FolderMetadata):
                    files.append({
                        'name': metadata.name,
                        'path': metadata.path_display,
                        'id': metadata.id,
                        'type': 'folder'
                    })

            logger.info(f"Found {len(files)} results for query '{query}'")
            return files

        except dropbox.exceptions.ApiError as e:
            logger.error(f"Error searching files for account {resolved_account}: {e}")
            return []

    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetches recently modified files for a specific account."""
        client, resolved_account = self._get_client_for_account(account)

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        logger.info(f"Fetching recent files for Dropbox account {resolved_account} since {since}")

        try:
            # List all files and filter by modification date
            result = client.files_list_folder("", recursive=True)
            recent_files = []

            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    if entry.client_modified and entry.client_modified >= since:
                        recent_files.append({
                            'name': entry.name,
                            'path': entry.path_display,
                            'size': entry.size,
                            'modified': entry.client_modified.isoformat(),
                            'id': entry.id,
                            'account': resolved_account
                        })

            return recent_files
        except Exception as e:
            logger.error(f"Error fetching recent data for account {resolved_account}: {e}")
            return []

    async def get_changed_files_since(self, cursor: Optional[str], *, account: Optional[str] = None) -> Tuple[List[Dict], Optional[str]]:
        """
        Get changed files since cursor using list_folder/continue.

        Args:
            cursor: Dropbox cursor for incremental sync. If None, performs initial sync.
            account: Dropbox account identifier

        Returns:
            Tuple of (files_list, new_cursor)
        """
        client, resolved_account = self._get_client_for_account(account)

        try:
            if cursor:
                # Continue from cursor
                result = client.files_list_folder_continue(cursor)
            else:
                # Initial sync - list all files recursively
                result = client.files_list_folder("", recursive=True)

            files = []
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    files.append({
                        'id': entry.id,
                        'name': entry.name,
                        'path': entry.path_display,
                        'size': entry.size,
                        'modified': entry.client_modified.isoformat() if entry.client_modified else None,
                        'account': resolved_account
                    })

            new_cursor = result.cursor
            logger.info(f"Fetched {len(files)} changed files for Dropbox account {resolved_account}")
            return files, new_cursor

        except dropbox.exceptions.ApiError as e:
            logger.error(f"Error fetching Dropbox changes for {resolved_account}: {e}")
            return [], None
        except Exception as e:
            logger.error(f"Unexpected error fetching Dropbox changes for {resolved_account}: {e}")
            return [], None
    