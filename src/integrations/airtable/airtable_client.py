import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from src.config.settings import settings
import base64

logger = setup_logger(__name__)

class AirtableIntegration(BaseIntegration):
    """Client for interacting with the Airtable API."""

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.api_base = "https://api.airtable.com/v0"

    async def _refresh_token_if_needed(self, token_info: Dict[str, Any]) -> Dict[str, Any]:
        """Check if token is expired and refresh it using Airtable API if needed."""
        if not token_info or not token_info.get("refresh_token"):
            return token_info
            
        expiry = token_info.get("token_expiry")
        if not expiry:
            return token_info
            
        if isinstance(expiry, datetime):
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            is_expired = datetime.now(timezone.utc) >= (expiry - timedelta(minutes=5))
        else:
            return token_info
            
        if not is_expired:
            return token_info
            
        logger.info(f"Airtable token for user {self.user_id} has expired. Refreshing...")
        
        try:
            url = "https://airtable.com/oauth2/v1/token"
            payload = {
                "grant_type": "refresh_token",
                "client_id": settings.AIRTABLE_CLIENT_ID,
                "refresh_token": token_info["refresh_token"]
            }
            
            auth_str = f"{settings.AIRTABLE_CLIENT_ID}:{settings.AIRTABLE_CLIENT_SECRET}"
            encoded_auth = base64.b64encode(auth_str.encode()).decode()
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, 
                    data=payload,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Authorization": f"Basic {encoded_auth}"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token", token_info["refresh_token"])
            expires_in = data.get("expires_in", 3600)
            new_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            await integration_service.update_integration_token_and_refresh_token(
                self.user_id, "airtable", new_access_token, new_expiry, new_refresh_token
            )
            
            logger.info(f"Airtable token successfully refreshed and updated for user {self.user_id}.")
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_expiry": new_expiry,
                "scopes": token_info.get("scopes", [])
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh Airtable token for user {self.user_id}: {e}")
            return token_info 

    async def authenticate(self) -> bool:
        try:
            token_info = await integration_service.get_integration_token(self.user_id, 'airtable')
            token_info = await self._refresh_token_if_needed(token_info)
            return bool(token_info and token_info.get('access_token'))
        except Exception as e:
            logger.error(f"Failed to authenticate Airtable for user {self.user_id}: {e}")
            return False

    async def _get_headers(self) -> Dict[str, str]:
        token_info = await integration_service.get_integration_token(self.user_id, 'airtable')
        token_info = await self._refresh_token_if_needed(token_info)
        
        if not token_info or not token_info.get('access_token'):
            raise Exception("No valid Airtable token available")
        return {
            "Authorization": f"Bearer {token_info['access_token']}",
            "Content-Type": "application/json"
        }

    async def fetch_recent_data(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recently modified data if applicable."""
        return []

    async def get_bases(self) -> List[Dict[str, Any]]:
        """Fetch a list of bases the user has access to."""
        try:
            headers = await self._get_headers()
            url = f"https://api.airtable.com/v0/meta/bases"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get("bases", [])
        except Exception as e:
            logger.error(f"Error fetching Airtable bases: {e}", exc_info=True)
            raise

    async def get_base_schema(self, base_id: str) -> Dict[str, Any]:
        """Fetch the schema (tables and columns) of a specific base."""
        try:
            headers = await self._get_headers()
            url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching Airtable base schema: {e}", exc_info=True)
            raise

    async def search_records(self, base_id: str, table_id_or_name: str, formula: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Search records in a specific base and table."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/{base_id}/{table_id_or_name}"
            
            params = {"maxRecords": limit}
            if formula:
                params["filterByFormula"] = formula
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                return data.get("records", [])
        except Exception as e:
            logger.error(f"Error searching Airtable records: {e}", exc_info=True)
            raise

    async def create_record(self, base_id: str, table_id_or_name: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record in a specific base and table."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/{base_id}/{table_id_or_name}"
            
            payload = {
                "records": [
                    {
                        "fields": fields
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("records", [{}])[0]
        except Exception as e:
            logger.error(f"Error creating Airtable record: {e}", exc_info=True)
            raise

    async def update_record(self, base_id: str, table_id_or_name: str, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing record in a specific base and table."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/{base_id}/{table_id_or_name}/{record_id}"
            
            payload = {
                "fields": fields
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.patch(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error updating Airtable record: {e}", exc_info=True)
            raise

    async def delete_record(self, base_id: str, table_id_or_name: str, record_id: str) -> bool:
        """Delete a record from a specific base and table."""
        try:
            headers = await self._get_headers()
            url = f"{self.api_base}/{base_id}/{table_id_or_name}/{record_id}"
            
            async with httpx.AsyncClient() as client:
                response = await client.delete(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get("deleted", False)
        except Exception as e:
            logger.error(f"Error deleting Airtable record: {e}", exc_info=True)
            raise