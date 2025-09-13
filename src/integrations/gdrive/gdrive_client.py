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

    async def search_files(self, query: str, max_results: int = 20) -> List[Dict]:
        """Search for files in Google Drive."""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")
        
        try:
            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, mimeType, modifiedTime, size, webViewLink, parents)"
            ).execute()
            
            return results.get('files', [])
        except Exception as e:
            logger.error(f"Error searching Google Drive files: {e}")
            raise Exception(f"Failed to search files: {e}")

    async def read_document_content(self, file_id: str, mime_type: str) -> str:
        """Read content from Google Docs, Sheets, or other document types."""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")
        
        try:
            # Handle Google Docs, Sheets, and Slides by exporting to plain text
            if mime_type == 'application/vnd.google-apps.document':
                # Google Docs - export as plain text
                request = self.service.files().export_media(fileId=file_id, mimeType='text/plain')
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                # Google Sheets - export as CSV
                request = self.service.files().export_media(fileId=file_id, mimeType='text/csv')
            elif mime_type == 'application/vnd.google-apps.presentation':
                # Google Slides - export as plain text
                request = self.service.files().export_media(fileId=file_id, mimeType='text/plain')
            else:
                # For other file types, try regular download
                request = self.service.files().get_media(fileId=file_id)
            
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            fh.seek(0)
            content = fh.read()
            
            # Try to decode as UTF-8, fall back to latin-1 if needed
            try:
                return content.decode('utf-8')
            except UnicodeDecodeError:
                return content.decode('latin-1', errors='replace')
                
        except Exception as e:
            logger.error(f"Error reading document content for file {file_id}: {e}")
            raise Exception(f"Failed to read document content: {e}")

    async def read_file_from_drive(self, file_name: str) -> str:
        """Reads the content of a file from Google Drive by its name."""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")

        # Search for the file by name (expanded to handle various file types)
        results = self.service.files().list(
            q=f"name='{file_name}'",
            pageSize=1,
            fields="files(id, name, mimeType)"
        ).execute()
        
        items = results.get('files', [])
        if not items:
            raise Exception(f"File not found: {file_name}")
        
        file_id = items[0]['id']
        mime_type = items[0]['mimeType']
        
        # Handle different file types
        if mime_type in ['application/vnd.google-apps.document', 
                        'application/vnd.google-apps.spreadsheet',
                        'application/vnd.google-apps.presentation']:
            return await self.read_document_content(file_id, mime_type)
        elif mime_type == 'text/plain' or mime_type.startswith('text/'):
            # Handle text files
            content = await self.download_file(file_id)
            if content:
                return content.decode('utf-8')
            else:
                raise Exception(f"Failed to download file: {file_name}")
        else:
            raise Exception(f"Unsupported file type for reading: {mime_type}. Supported types: Google Docs, Sheets, Slides, and text files.")