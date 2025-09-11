from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime

class BaseIntegration(ABC):
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.last_sync = None
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the service"""
        pass
    
    @abstractmethod
    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent data since last sync"""
        pass
    
    