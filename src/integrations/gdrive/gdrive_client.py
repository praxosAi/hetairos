import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger

logger = setup_logger('gdrive_client')

class GoogleDriveIntegration(BaseIntegration):

    def __init__(self, user_id: str):
        super().__init__(user_id)
        # Manages multiple service instances, one per connected account
        self.services: Dict[str, Any] = {}
        self.credentials: Dict[str, Any] = {}
        self.connected_accounts: List[str] = []

    async def authenticate(self) -> bool:
        """Authenticates all connected Google Drive accounts for the user."""
        logger.info(f"Authenticating all Google Drive accounts for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(self.user_id, 'google_drive')

        if not integration_records:
            logger.warning(f"No Google Drive integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record
        ]
        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict[str, Any]) -> bool:
        """Authenticates a single account using its unique integration ID."""
        account_email = integration_record.get('connected_account')
        integration_id = integration_record.get('_id')

        if not account_email or not integration_id:
            logger.warning(f"Drive integration record for {self.user_id} is missing '_id' or 'connected_account'.")
            return False

        creds = await integration_service.create_google_credentials(self.user_id, 'google_drive', str(integration_id))
        
        if not creds:
            logger.error(f"Failed to create credentials for Drive account {account_email}")
            return False

        try:
            service = build('drive', 'v3', credentials=creds)
            self.services[account_email] = service
            self.credentials[account_email] = creds
            if account_email not in self.connected_accounts:
                self.connected_accounts.append(account_email)
            logger.info(f"Successfully authenticated Drive for {account_email}")
            return True
        except Exception as e:
            logger.error(f"Error building service for Drive account {account_email}: {e}")
            return False
            
    def get_connected_accounts(self) -> List[str]:
        return self.connected_accounts

    def _get_service_for_account(self, account: Optional[str] = None) -> Tuple[Any, str]:
        """Retrieves the correct service instance and resolved account email."""
        if account:
            service = self.services.get(account)
            if not service:
                raise ValueError(f"Account '{account}' is not authenticated or does not exist.")
            return service, account
        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.services[default_account], default_account
        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Google Drive accounts found.")
        raise ValueError(f"Multiple accounts exist. Specify one with the 'account' parameter: {self.connected_accounts}")

    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recently modified files from a specific Google Drive account."""
        service, resolved_account = self._get_service_for_account(account)
        
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)
        since_str = since.isoformat() + 'Z'
        
        try:
            results = service.files().list(
                q=f"modifiedTime > '{since_str}' and trashed=false",
                pageSize=100,
                fields="files(id, name, mimeType, modifiedTime, size)"
            ).execute()
            return results.get('files', [])
        except Exception as e:
            logger.error(f"Error fetching files for {resolved_account}: {e}")
            return []

    def get_user_info(self, *, account: Optional[str] = None) -> Dict:
        """Gets a specific authenticated user's Google Drive account information."""
        service, resolved_account = self._get_service_for_account(account)
        
        try:
            about = service.about().get(fields="user,storageQuota").execute()
            user = about.get('user', {})
            storage = about.get('storageQuota', {})
            
            return {
                'display_name': user.get('displayName', ''),
                'email': user.get('emailAddress', ''),
                'photo_link': user.get('photoLink', ''),
                'storage_limit': storage.get('limit', ''),
                'storage_usage': storage.get('usage', ''),
            }
        except Exception as e:
            logger.error(f"Error fetching user info for {resolved_account}: {e}")
            raise Exception(f"Failed to get user info for {resolved_account}: {e}")

    async def download_file(self, file_id: str, *, account: Optional[str] = None) -> Optional[bytes]:
        """Download a file from a specific Google Drive account."""
        service, resolved_account = self._get_service_for_account(account)
        
        try:
            request = service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            fh.seek(0)
            return fh.read()
        except Exception as e:
            logger.error(f"Error downloading file {file_id} from {resolved_account}: {e}")
            return None

    async def save_file_to_drive(self, file_url: str, file_name: str, *, drive_folder_id: Optional[str] = None, account: Optional[str] = None) -> str:
        """Downloads a file from a URL and saves it to a specific Google Drive account."""
        service, resolved_account = self._get_service_for_account(account)
        
        try:
            response = requests.get(file_url, stream=True)
            response.raise_for_status()
            
            file_metadata = {'name': file_name}
            if drive_folder_id:
                file_metadata['parents'] = [drive_folder_id]

            media = MediaIoBaseUpload(BytesIO(response.content), mimetype=response.headers.get('content-type'), resumable=True)
            
            uploaded_file = service.files().create(
                body=file_metadata, media_body=media, fields='id, webViewLink'
            ).execute()

            return f"File '{file_name}' uploaded to {resolved_account}. Link: {uploaded_file.get('webViewLink')}"
        except Exception as e:
            raise Exception(f"Error uploading file to {resolved_account}: {e}")

    async def create_text_file(self, filename: str, content: str, *, drive_folder_id: Optional[str] = None, account: Optional[str] = None) -> Dict:
        """Creates a new text file in a specific Google Drive account."""
        service, resolved_account = self._get_service_for_account(account)
        
        file_metadata = {'name': filename, 'mimeType': 'text/plain'}
        if drive_folder_id:
            file_metadata['parents'] = [drive_folder_id]
        
        media = MediaIoBaseUpload(BytesIO(content.encode()), mimetype='text/plain', resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        logger.info(f"Created text file '{filename}' in {resolved_account}")
        return file

    async def read_file_content_by_id(self, file_id: str, *, account: Optional[str] = None) -> str:
        """Reads the content of a file from a specific Google Drive account."""
        service, resolved_account = self._get_service_for_account(account)

        try:
            file_metadata = service.files().get(fileId=file_id, fields="mimeType").execute()
            mime_type = file_metadata.get('mimeType', '')

            if mime_type.startswith('text/') or mime_type in ['application/json', 'application/xml']:
                # Pass the account context to the internal download call
                content = await self.download_file(file_id, account=resolved_account)
                return content.decode('utf-8')
            elif 'google-apps' in mime_type:
                export_mime_type = 'text/plain'
                if 'spreadsheet' in mime_type:
                    export_mime_type = 'text/csv'
                elif 'presentation' in mime_type:
                     # Exporting presentations as text can be noisy, but it's an option
                    export_mime_type = 'text/plain'

                request = service.files().export_media(fileId=file_id, mimeType=export_mime_type)
                fh = BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                fh.seek(0)
                return fh.read().decode('utf-8')
            else:
                return f"Cannot read content: unsupported file type ({mime_type})."

        except Exception as e:
            raise Exception(f"Error reading file content from {resolved_account}: {e}")

    async def list_files(self, *, query: Optional[str] = None, max_results: int = 50, folder_id: Optional[str] = None, account: Optional[str] = None) -> List[Dict]:
        """Lists files in a specific Google Drive account."""
        service, resolved_account = self._get_service_for_account(account)

        try:
            q_parts = ["trashed=false"]
            if folder_id:
                q_parts.append(f"'{folder_id}' in parents")
            if query:
                q_parts.append(f"name contains '{query}'")
            q_string = " and ".join(q_parts)

            results = service.files().list(
                q=q_string,
                pageSize=min(max_results, 1000),
                fields="files(id, name, mimeType, modifiedTime, size, webViewLink)"
            ).execute()

            return [{
                'id': f.get('id'),
                'name': f.get('name'),
                'type': f.get('mimeType', 'unknown'),
                'modified': f.get('modifiedTime'),
                'size_bytes': f.get('size'),
                'link': f.get('webViewLink')
            } for f in results.get('files', [])]
        except Exception as e:
            raise Exception(f"Failed to list files for {resolved_account}: {e}")