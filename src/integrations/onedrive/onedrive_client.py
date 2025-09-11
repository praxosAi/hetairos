from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import aiohttp
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)

class OneDriveIntegration(BaseIntegration):
    
    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.access_token = None
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"

    async def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API for OneDrive using user-specific tokens."""
        try:
            token_info = await integration_service.get_integration_token(self.user_id, 'onedrive')
            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve OneDrive token for user {self.user_id}")
                return False
            
            self.access_token = token_info['access_token']
            return True
        except Exception as e:
            logger.error(f"OneDrive authentication failed for user {self.user_id}: {e}")
            return False

    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recently modified files from OneDrive."""
        if not self.access_token:
            return []
        
        # The Microsoft Graph API for recent files doesn't use a 'since' parameter.
        # It returns the most recently used files, which is a good proxy.
        url = f"{self.graph_endpoint}/me/drive/recent"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data.get('value', [])
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching recent OneDrive files for user {self.user_id}: {e}")
            return []

    async def download_file(self, file_id: str) -> Optional[bytes]:
        """Download a file from OneDrive."""
        if not self.access_token:
            return None
        
        url = f"{self.graph_endpoint}/me/drive/items/{file_id}/content"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    return await response.read()
        except aiohttp.ClientError as e:
            logger.error(f"Error downloading file {file_id} from OneDrive: {e}")
            return None
