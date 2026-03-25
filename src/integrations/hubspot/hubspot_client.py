import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

class HubSpotIntegration(BaseIntegration):
    """Client for interacting with the HubSpot CRM API."""

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.api_base = "https://api.hubapi.com"

    async def authenticate(self) -> bool:
        try:
            token_info = await integration_service.get_integration_token(self.user_id, 'hubspot')
            return bool(token_info and token_info.get('access_token'))
        except Exception as e:
            logger.error(f"Failed to authenticate HubSpot for user {self.user_id}: {e}")
            return False

    async def _get_headers(self) -> Dict[str, str]:
        token_info = await integration_service.get_integration_token(self.user_id, 'hubspot')
        if not token_info or not token_info.get('access_token'):
            raise Exception("No valid HubSpot token available")
        return {
            "Authorization": f"Bearer {token_info['access_token']}",
            "Content-Type": "application/json"
        }

    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recently modified contacts as a default data sync method."""
        return await self.search_contacts(limit=10)

    async def search_contacts(self, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Search for HubSpot contacts."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/crm/v3/objects/contacts/search"
            
            payload = {
                "limit": limit,
                "properties": ["firstname", "lastname", "email", "phone", "company", "lifecyclestage"]
            }
            if query:
                payload["filterGroups"] = [{
                    "filters": [{
                        "propertyName": "email",
                        "operator": "CONTAINS_TOKEN",
                        "value": f"*{query}*"
                    }]
                }] # Note: Full text search usually requires specific indexing or filtering.
                   # For simple email queries this works well. We can also just fetch all and filter.
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
        except Exception as e:
            logger.error(f"Error searching HubSpot contacts: {e}", exc_info=True)
            raise

    async def create_contact(self, properties: Dict[str, str]) -> Dict[str, Any]:
        """Create a new HubSpot contact."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/crm/v3/objects/contacts"
            
            payload = {"properties": properties}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error creating HubSpot contact: {e}", exc_info=True)
            raise

    async def search_companies(self, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Search for HubSpot companies."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/crm/v3/objects/companies/search"
            
            payload = {
                "limit": limit,
                "properties": ["name", "domain", "industry", "phone", "city"]
            }
            if query:
                payload["filterGroups"] = [{
                    "filters": [{
                        "propertyName": "name",
                        "operator": "CONTAINS_TOKEN",
                        "value": f"*{query}*"
                    }]
                }]
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
        except Exception as e:
            logger.error(f"Error searching HubSpot companies: {e}", exc_info=True)
            raise

    async def create_company(self, properties: Dict[str, str]) -> Dict[str, Any]:
        """Create a new HubSpot company."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/crm/v3/objects/companies"
            
            payload = {"properties": properties}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error creating HubSpot company: {e}", exc_info=True)
            raise

    async def create_deal(self, properties: Dict[str, str]) -> Dict[str, Any]:
        """Create a new HubSpot deal."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/crm/v3/objects/deals"
            
            payload = {"properties": properties}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error creating HubSpot deal: {e}", exc_info=True)
            raise
    async def create_note(self, body: str, contact_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a note and optionally associate it with a contact."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/crm/v3/objects/notes"
            
            payload = {
                "properties": {
                    "hs_note_body": body
                }
            }
            
            if contact_id:
                payload["associations"] = [
                    {
                        "to": {"id": contact_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}] # 202 is Note -> Contact
                    }
                ]
                
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error creating HubSpot note: {e}", exc_info=True)
            raise

    async def create_task(self, subject: str, body: str = "", contact_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a task and optionally associate it with a contact."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/crm/v3/objects/tasks"
            
            payload = {
                "properties": {
                    "hs_task_subject": subject,
                    "hs_task_body": body,
                    "hs_task_status": "NOT_STARTED"
                }
            }
            
            if contact_id:
                payload["associations"] = [
                    {
                        "to": {"id": contact_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}] # 204 is Task -> Contact
                    }
                ]
                
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error creating HubSpot task: {e}", exc_info=True)
            raise
