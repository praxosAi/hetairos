import dropbox
from typing import Optional
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from typing import List, Dict
from datetime import datetime
logger = setup_logger(__name__)

class DropboxIntegration(BaseIntegration):
    
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.client = None

    async def authenticate(self) -> bool:
        """Authenticate with Dropbox API using user-specific tokens."""
        try:
            token_info = await integration_service.get_integration_token(self.user_id, 'dropbox')
            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve Dropbox token for user {self.user_id}")
                return False
            
            # TODO: Add token refresh logic for Dropbox if needed
            
            self.client = dropbox.Dropbox(token_info['access_token'])
            return True
        except Exception as e:
            logger.error(f"Dropbox authentication failed for user {self.user_id}: {e}")
            return False

    async def save_file(self, file_path: str, content: bytes):
        """Saves a file to Dropbox."""
        if not self.client:
            raise Exception("Dropbox client not initialized.")
        
        self.client.files_upload(content, file_path)

    async def read_file(self, file_path: str) -> bytes:
        """Reads a file from Dropbox."""
        if not self.client:
            raise Exception("Dropbox client not initialized.")
            
        _, res = self.client.files_download(path=file_path)
        return res.content


    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        pass
    