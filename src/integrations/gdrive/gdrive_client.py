from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from io import BytesIO
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import requests
from src.utils.logging.base_logger import setup_logger

from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service

logger = setup_logger(__name__)

class GoogleDriveIntegration(BaseIntegration):
    SCOPES = ['https://www.googleapis.com/auth/drive.file',
              'https://www.googleapis.com/auth/drive.readonly']
    
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.service = None
        self.credentials = None
        self.user_info = None

    async def authenticate(self) -> bool:
        """Authenticate with Google Drive API using user-specific tokens."""
        try:
            self.credentials = await integration_service.create_google_credentials(self.user_id, 'google_drive')
            if not self.credentials:
                logger.error(f"Failed to create Google Drive credentials for user {self.user_id}")
                return False
            
            self.service = build('drive', 'v3', credentials=self.credentials)
            return True
        except Exception as e:
            logger.error(f"Google Drive authentication failed for user {self.user_id}: {e}")
            return False

    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recently modified files from Google Drive."""
        if not self.service:
            return []
        
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)
        
        since_str = since.isoformat() + 'Z'
        
        try:
            results = self.service.files().list(
                q=f"modifiedTime > '{since_str}'",
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)"
            ).execute()
            
            files = results.get('files', [])
            return files
        except Exception as e:
            logger.error(f"Error fetching Google Drive files for user {self.user_id}: {e}")
            return []

    def get_user_info(self) -> Dict:
        """Gets the authenticated user's Google Drive account information."""
        if self.user_info:
            return self.user_info

        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")
        
        try:
            about = self.service.about().get(fields="user,storageQuota").execute()
            user = about.get('user', {})
            storage = about.get('storageQuota', {})
            
            self.user_info = {
                'display_name': user.get('displayName', ''),
                'email': user.get('emailAddress', ''),
                'photo_link': user.get('photoLink', ''),
                'storage_limit': storage.get('limit', ''),
                'storage_usage': storage.get('usage', ''),
                'storage_usage_in_drive': storage.get('usageInDrive', '')
            }
            return self.user_info
        except Exception as e:
            logger.error(f"Error fetching user info: {e}")
            raise Exception(f"Failed to get user info: {e}")

    async def download_file(self, file_id: str) -> Optional[bytes]:
        """Download a file from Google Drive."""
        if not self.service:
            return None
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            fh.seek(0)
            return fh.read()
        except Exception as e:
            logger.error(f"Error downloading file {file_id} from Google Drive: {e}")
            return None

    async def save_file_to_drive(self, file_url: str, file_name: str, drive_folder_id: Optional[str] = None) -> str:
        """Downloads a file from a URL and saves it to Google Drive."""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")
        
        try:
            response = requests.get(file_url, stream=True)
            response.raise_for_status()
            
            file_content = BytesIO(response.content)
            content_type = response.headers.get('content-type', 'application/octet-stream')

            file_metadata = {'name': file_name}
            if drive_folder_id:
                file_metadata['parents'] = [drive_folder_id]

            media = MediaIoBaseUpload(file_content, mimetype=content_type, resumable=True)
            
            uploaded_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            return f"File '{file_name}' uploaded successfully. View it here: {uploaded_file.get('webViewLink')}"
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error downloading the file: {e}")
        except Exception as e:
            raise Exception(f"Error uploading file to Google Drive: {e}")

    async def create_text_file(self, filename: str, content: str, drive_folder_id: Optional[str] = None) -> Dict:
        """Creates a new text file in Google Drive."""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")
        
        file_metadata = {'name': filename, 'mimeType': 'text/plain'}
        if drive_folder_id:
            file_metadata['parents'] = [drive_folder_id]
        
        media = MediaIoBaseUpload(BytesIO(content.encode()), mimetype='text/plain', resumable=True)
        
        file = self.service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file

    async def read_file_from_drive(self, file_name: str) -> str:
        """Reads the content of a text file from Google Drive by its name."""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")

        # Find the file by name
        results = self.service.files().list(
            q=f"name='{file_name}' and mimeType='text/plain'",
            pageSize=1,
            fields="files(id, name)"
        ).execute()

        items = results.get('files', [])
        if not items:
            raise Exception(f"File not found: {file_name}")

        file_id = items[0]['id']

        # Download and read the file content
        content = await self.download_file(file_id)
        return content.decode('utf-8')

    async def list_files(self, query: Optional[str] = None, max_results: int = 50, folder_id: Optional[str] = None) -> List[Dict]:
        """Lists files in Google Drive with optional search query and folder filtering."""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")

        try:
            # Build the query string
            q_parts = []

            if folder_id:
                q_parts.append(f"'{folder_id}' in parents")

            if query:
                q_parts.append(f"name contains '{query}'")

            # Exclude trashed files
            q_parts.append("trashed=false")

            q_string = " and ".join(q_parts)

            results = self.service.files().list(
                q=q_string,
                pageSize=min(max_results, 1000),  # Google Drive API max is 1000
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink, parents)"
            ).execute()

            files = results.get('files', [])

            # Format the response for better readability
            formatted_files = []
            for file in files:
                formatted_file = {
                    'id': file.get('id'),
                    'name': file.get('name'),
                    'type': file.get('mimeType', '').split('/')[-1] if file.get('mimeType') else 'unknown',
                    'modified': file.get('modifiedTime'),
                    'size': file.get('size', 'N/A'),
                    'link': file.get('webViewLink'),
                    'parents': file.get('parents', [])
                }
                formatted_files.append(formatted_file)

            return formatted_files

        except Exception as e:
            logger.error(f"Error listing Google Drive files for user {self.user_id}: {e}")
            raise Exception(f"Failed to list files: {e}")