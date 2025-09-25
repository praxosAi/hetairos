import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.config.settings import settings
from src.utils.database import db_manager
from src.services.token_encryption import decrypt_token, encrypt_token
from bson import ObjectId
from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)
import json

class IntegrationService:
    """Manages all user integrations, including capabilities and authentication."""

    def __init__(self):
        self.db_manager = db_manager
        self.integration_capabilities = {
            "gmail": ["read_emails", "search_emails", "send_emails", "sync_history"],
            "google_calendar": ["read_events", "create_events", "update_events"],
        }

    async def update_integration_token(self, user_id: str, integration_name: str, new_token: str, new_expiry: datetime):
        """Encrypts and updates a new access token in the database."""
        try:
            encrypted_token = encrypt_token(new_token)
            await self.db_manager.db["integration_tokens"].update_one(
                {"user_id": ObjectId(user_id), "integration_name": integration_name},
                {"$set": {
                    "access_token_encrypted": encrypted_token,
                    "token_expiry": new_expiry,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"Successfully updated and encrypted token for user {user_id}, provider {integration_name}.")
        except Exception as e:
            logger.error(f"Failed to update token for user {user_id}, provider {integration_name}: {e}")


    async def update_integration_token_and_refresh_token(self, user_id: str, integration_name: str, new_token: str, new_expiry: datetime, new_refresh_token: str    ):
        """Encrypts and updates a new access token in the database."""
        try:
            encrypted_token = encrypt_token(new_token)
            encrypted_refresh_token = encrypt_token(new_refresh_token)
            await self.db_manager.db["integration_tokens"].update_one(
                {"user_id": ObjectId(user_id), "integration_name": integration_name},
                {"$set": {
                    "access_token_encrypted": encrypted_token,
                    "refresh_token_encrypted": encrypted_refresh_token,
                    "token_expiry": new_expiry,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"Successfully updated and encrypted token for user {user_id}, provider {integration_name}.")
        except Exception as e:
            logger.error(f"Failed to update token for user {user_id}, provider {integration_name}: {e}")
    async def get_user_integrations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all of a user's configured integrations."""
        return await self.db_manager.db["integrations"].find({"user_id": ObjectId(user_id)}).to_list(length=100)

    async def get_user_integrations_llm_info(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all of a user's configured integrations without userid and id and other sensitive information."""
        integrations = await self.db_manager.db["integrations"].find({"user_id": ObjectId(user_id)}).to_list(length=100)
        for integ in integrations:
            integ.pop("sync_frequency", None)
            integ.pop("_id", None)
            integ.pop("user_id", None)
        return integrations
    async def get_integration_record_for_user_and_name(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Get the integration record for a specific user and name."""
        integration_record = await self.db_manager.db["integrations"].find_one({"user_id": ObjectId(user_id), "name": name})
        if integration_record:
            return integration_record
        else:
            return None



    async def get_integration_token(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Get the decrypted token for a specific user and provider."""
        if settings.OPERATING_MODE == "local":
            logger.info(f"Operating in local mode. Fetching token for {name} from settings.")
            if name == "google_calendar" or name == "gmail":
                return {
                    "access_token": "local_google_access_token",  # This would be fetched or refreshed
                    "refresh_token": settings.GOOGLE_REFRESH_TOKEN,
                    "token_expiry": None,  # Local tokens might not have an expiry or are long-lived
                    "scopes": ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/gmail.readonly"]
                }
            elif name == "microsoft":
                 return {
                    "access_token": "local_microsoft_access_token",
                    "refresh_token": settings.MICROSOFT_REFRESH_TOKEN,
                    "token_expiry": None,
                    "scopes": ["user.read", "mail.read"]
                }
            # Add other integrations here as needed
            logger.warning(f"No local token configuration for provider {name}")
            return None

        token_doc = await self.db_manager.db["integration_tokens"].find_one({
            "user_id": ObjectId(user_id),
            "integration_name": name
        })
        # logger.info(f"token_doc: {json.dumps(token_doc,indent=4,default=str)}")
        if not token_doc:
            logger.warning(f"No token found for user {user_id} and provider {name}")
            return None

        try:
            access_token = decrypt_token(token_doc.get("access_token_encrypted"))
            refresh_token = decrypt_token(token_doc.get("refresh_token_encrypted")) if token_doc.get(
                "refresh_token_encrypted") else None

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expiry": token_doc.get("token_expiry"),
                "scopes": token_doc.get("scopes", [])
            }
        except Exception as e:
            logger.error(f"Failed to decrypt token for user {user_id}, provider {name}: {e}")
            return None
    async def is_authorized_user(self, integration_name: str, connected_account: str) -> bool:
        """Check if a phone number belongs to an authorized user"""
        integration = await self.db_manager.db["integrations"].find_one({"name": integration_name, "connected_account": connected_account})
        if integration:
            return integration
        else:
            return False
    async def create_google_credentials(self, user_id: str, name: str) -> Optional[Credentials]:
        """Creates a Google Credentials object from a user's stored token."""
        token_doc = await self.get_integration_token(user_id, name)
        if not token_doc:
            return None

        try:
            creds = Credentials(
                token=token_doc.get("access_token"),
                refresh_token=token_doc.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                scopes=token_doc.get("scopes"),
                expiry=token_doc.get("token_expiry")
            )

            # --- TOKEN REFRESH LOGIC ---
            if creds and creds.expired and creds.refresh_token:
                logger.info(f"Token for user {user_id}, provider {name} has expired. Refreshing...")
                creds.refresh(Request())
                # Persist the new token
                await self.update_integration_token_and_refresh_token(user_id, name, creds.token, creds.expiry, creds.refresh_token)
                logger.info(f"Token refreshed and updated successfully for user {user_id}, provider {name}.")
            # -------------------------

            return creds
        except Exception as e:
            logger.error(f"Failed to create or refresh Google credentials for user {user_id}: {e}")
            return None
    # async def create_microsoft_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
    #     """Get the Microsoft credentials for a user."""
    #     token_doc = await self.get_integration_token(user_id, "microsoft")
    #     if token_doc:
    #         return token_doc
    #     try:
    #         creds = Credentials(
    #             token=token_doc.get("access_token"),
    #             refresh_token=token_doc.get("refresh_token"),
    #             token_uri="https://oauth2.googleapis.com/token",
    #             client_id=settings.MICROSOFT_CLIENT_ID,
    #             client_secret=settings.MICROSOFT_CLIENT_SECRET,
    #             scopes=token_doc.get("scopes"),
    #             expiry=token_doc.get("token_expiry")
    #         )
    #         if creds and creds.expired and creds.refresh_token:
    #             logger.info(f"Token for user {user_id}, provider Microsoft has expired. Refreshing...")
    #             creds.refresh(Request())
    #             # Persist the new token
    #             await self.update_integration_token(user_id, "microsoft", creds.token, creds.expiry)
    #             logger.info(f"Token refreshed and updated successfully for user {user_id}, provider Microsoft.")
    #         return creds
    #     except Exception as e:
    #         logger.error(f"Failed to create Microsoft credentials for user {user_id}: {e}")
    #         return None
    async def get_authenticated_clients(self, user_id: str) -> Dict[str, Any]:
        """
        Creates and returns a dictionary of all authenticated API clients for a user.
        """
        clients = {}
        integrations = await self.get_user_integrations(user_id)
        
        for integration in integrations:
            name = integration.get("name")
            if name == "google_calendar":
                creds = await self.create_google_credentials(user_id, name)
                if creds:
                    clients["google_calendar"] = build('calendar', 'v3', credentials=creds)
            elif name == "gmail":
                creds = await self.create_google_credentials(user_id, name)
                if creds:
                    clients["gmail"] = build('gmail', 'v1', credentials=creds)
            # Add other providers here as needed
            
        return clients
    



    async def get_user_by_integration(self, type: str, connected_account:str) -> Optional[List[str]]:
        """Get the user id by the integration type and connected account."""

        integrations = await self.db_manager.db["integrations"].find({"type": type, "connected_account": connected_account}).to_list(length=100)

        if not integrations:
            return None

        return [str(integration.get("user_id")) for integration in integrations]
    async def get_user_by_integration_name(self, name: str,connected_account:str) -> Optional[List[str]]:
        """Get the user id by the integration name and connected account."""
        integrations = await self.db_manager.db["integrations"].find({"name": name, "connected_account": connected_account}).to_list(length=100)

        if not integrations:
            return None

        return [str(integration.get("user_id")) for integration in integrations]
    async def update_integration(self, integration_id: str, integration: dict):
        """Update an integration."""
        await self.db_manager.db["integrations"].update_one({"_id": ObjectId(integration_id)}, {"$set": integration})
# Global instance
integration_service = IntegrationService()
