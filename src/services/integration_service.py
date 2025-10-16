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
from src.utils.redis_client import redis_client
from src.services.user_service import user_service
from src.services.milestone_service import milestone_service
import json
import re
import asyncio


logger = setup_logger(__name__)
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


    async def update_integration_token_and_refresh_token(self, user_id: str, integration_name: str, new_token: str, new_expiry: datetime, new_refresh_token: str, integration_id: str = None):
        """Encrypts and updates a new access token in the database."""
        try:
            encrypted_token = encrypt_token(new_token)
            encrypted_refresh_token = encrypt_token(new_refresh_token)
            query = {"user_id": ObjectId(user_id), "integration_name": integration_name}
            if integration_id:
                query["integration_id"] = ObjectId(integration_id)
            await self.db_manager.db["integration_tokens"].update_one(
                query,
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

    async def add_integration_for_messaging_app(self, user_id: str,  name: str, connected_account: str,telegram_chat_id = None) -> str:
        new_integration_record = {
            "user_id": ObjectId(user_id),
            'name': name,
            'type': 'messaging',
            'provider': name,
            'connected_account': connected_account,
            'status': 'active',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'metadata': {'connected_at': datetime.now(timezone.utc).isoformat(),'consent_timestamp': datetime.now(timezone.utc).isoformat(),'phone_verified': True},

        }
        if name == "telegram":
            new_integration_record['telegram_chat_id'] = telegram_chat_id
        
        result = await self.db_manager.db["integrations"].insert_one(new_integration_record)

        # Schedule milestone update in background with error handling
        async def _update_milestone_with_error_handling():
            try:
                await milestone_service.user_setup_messaging(user_id)
            except Exception as e:
                logger.error(f"Failed to update milestone for user {user_id}: {e}", exc_info=True)

        asyncio.create_task(_update_milestone_with_error_handling())

        # Sync integration to KG in background
        # async def _sync_to_kg():
        #     try:
        #         await self.sync_integration_to_kg(user_id, name, new_integration_record)
        #     except Exception as e:
        #         logger.error(f"Failed to sync integration {name} to KG for user {user_id}: {e}", exc_info=True)

        # asyncio.create_task(_sync_to_kg())

        if result:
            return new_integration_record
        else:
            return None
    async def get_integration_token(self, user_id: str, name: str,integration_id:str = None) -> Optional[Dict[str, Any]]:
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
        query = {
            "user_id": ObjectId(user_id),
            "integration_name": name
        }
        if integration_id:
            query["integration_id"] = ObjectId(integration_id)
        token_doc = await self.db_manager.db["integration_tokens"].find_one(query)

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
        integration = await self.db_manager.db["integrations"].find_one({"name": integration_name, "connected_account": connected_account,'status':'active'})
        if integration:
            return integration
        else:
            return False
        
    async def is_authorized_user_telegram_chat_id(self, telegram_chat_id) -> bool:
        """Check if a telegram chat ID belongs to an authorized user"""
        integration = await self.db_manager.db["integrations"].find_one({"name": "telegram", "telegram_chat_id": telegram_chat_id, 'status': 'active'})
        if integration:
            return integration
        else:
            return False

    async def is_authorizable_user(self, integration_name: str, connected_account: str, message_text: str=None, telegram_chat_id = None) -> bool:

        if not message_text:
            return False
        # Step 2: check for init handshake
        try:
            if "INITIALIZE COMMUNICATION PROTOCOL" in message_text.upper():
                # Step 3: extract code inside brackets
                match = re.search(r"\[(.*?)\]", message_text)
                if match:
                    auth_code = match.group(1).strip()
                    # Step 4: try to authorize using this code
                    redis_key = f"messaging_auth_code:{auth_code}"
                    try:
                        user_id = await redis_client.get(redis_key)
                        logger.info(f"Retrieved user_id {user_id} from Redis for auth_code {auth_code}")
                        if user_id:
                            # Check if the user exists
                            user =  user_service.get_user_by_id(user_id)
                            if user:
                                #### we can now create the integration record
                                new_record = await self.add_integration_for_messaging_app(user_id, integration_name, connected_account,telegram_chat_id)
                                if new_record:
                                    return new_record,user
                            else:
                                logger.warning(f"No user found with ID {user_id} for auth_code {auth_code}")
                    except Exception as e:
                        logger.error(f"Error retrieving user_id from Redis for auth_code {auth_code}: {e}")
        except Exception as e:
            logger.error(f"Error authorizing user for auth_code {auth_code}: {e}",exc_info=True)


        return False,None
    async def create_google_credentials(self, user_id: str, name: str, integration_id:str=None) -> Optional[Credentials]:
        """Creates a Google Credentials object from a user's stored token."""
        token_doc = await self.get_integration_token(user_id, name,integration_id)
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
                await self.update_integration_token_and_refresh_token(user_id, name, creds.token, creds.expiry, creds.refresh_token,integration_id)
                logger.info(f"Token refreshed and updated successfully for user {user_id}, provider {name}.")
            # -------------------------

            return creds
        except Exception as e:
            logger.error(f"Failed to create or refresh Google credentials for user {user_id}: {e}", exc_info=True)
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
    
    async def get_gmail_checkpoint(self, user_id: str, connected_account: str) -> Optional[str]:
        integ = await self.db_manager.db["integrations"].find_one(
            {"user_id": ObjectId(user_id), "name": "gmail", "connected_account": connected_account},
            projection={"gmail_history_checkpoint": 1}
        )
        return (integ or {}).get("gmail_history_checkpoint")

    async def set_gmail_checkpoint(self, user_id: str, connected_account: str, history_id: str) -> None:
        await self.db_manager.db["integrations"].update_one(
            {"user_id": ObjectId(user_id), "name": "gmail", "connected_account": connected_account},
            {"$set": {
                "gmail_history_checkpoint": str(history_id),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )

    # Google Calendar checkpoint methods
    async def get_calendar_sync_token(self, user_id: str, connected_account: str) -> Optional[str]:
        """Get the sync token for Google Calendar incremental sync."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"user_id": ObjectId(user_id), "name": "google_calendar", "connected_account": connected_account},
            projection={"calendar_sync_token": 1}
        )
        return (integ or {}).get("calendar_sync_token")

    async def set_calendar_sync_token(self, user_id: str, connected_account: str, sync_token: str) -> None:
        """Set the sync token for Google Calendar incremental sync."""
        await self.db_manager.db["integrations"].update_one(
            {"user_id": ObjectId(user_id), "name": "google_calendar", "connected_account": connected_account},
            {"$set": {
                "calendar_sync_token": str(sync_token),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )

    # Google Drive checkpoint methods
    async def get_drive_page_token(self, user_id: str, connected_account: str) -> Optional[str]:
        """Get the page token for Google Drive changes API."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"user_id": ObjectId(user_id), "name": "google_drive", "connected_account": connected_account},
            projection={"drive_page_token": 1}
        )
        return (integ or {}).get("drive_page_token")

    async def set_drive_page_token(self, user_id: str, connected_account: str, page_token: str) -> None:
        """Set the page token for Google Drive changes API."""
        await self.db_manager.db["integrations"].update_one(
            {"user_id": ObjectId(user_id), "name": "google_drive", "connected_account": connected_account},
            {"$set": {
                "drive_page_token": str(page_token),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )

    # Microsoft Calendar/OneDrive delta link methods
    async def get_outlook_calendar_delta_link(self, user_id: str, connected_account: str) -> Optional[str]:
        """Get the delta link for Outlook Calendar incremental sync."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"user_id": ObjectId(user_id), "name": "outlook_calendar", "connected_account": connected_account},
            projection={"calendar_delta_link": 1}
        )
        return (integ or {}).get("calendar_delta_link")

    async def set_outlook_calendar_delta_link(self, user_id: str, connected_account: str, delta_link: str) -> None:
        """Set the delta link for Outlook Calendar incremental sync."""
        await self.db_manager.db["integrations"].update_one(
            {"user_id": ObjectId(user_id), "name": "outlook_calendar", "connected_account": connected_account},
            {"$set": {
                "calendar_delta_link": str(delta_link),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )

    async def get_onedrive_delta_link(self, user_id: str, connected_account: str) -> Optional[str]:
        """Get the delta link for OneDrive incremental sync."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"user_id": ObjectId(user_id), "name": "onedrive", "connected_account": connected_account},
            projection={"onedrive_delta_link": 1}
        )
        return (integ or {}).get("onedrive_delta_link")

    async def set_onedrive_delta_link(self, user_id: str, connected_account: str, delta_link: str) -> None:
        """Set the delta link for OneDrive incremental sync."""
        await self.db_manager.db["integrations"].update_one(
            {"user_id": ObjectId(user_id), "name": "onedrive", "connected_account": connected_account},
            {"$set": {
                "onedrive_delta_link": str(delta_link),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )

    # Dropbox cursor methods
    async def get_dropbox_cursor(self, user_id: str, connected_account: str) -> Optional[str]:
        """Get the cursor for Dropbox incremental sync."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"user_id": ObjectId(user_id), "name": "dropbox", "connected_account": connected_account},
            projection={"dropbox_cursor": 1}
        )
        return (integ or {}).get("dropbox_cursor")

    async def set_dropbox_cursor(self, user_id: str, connected_account: str, cursor: str) -> None:
        """Set the cursor for Dropbox incremental sync."""
        await self.db_manager.db["integrations"].update_one(
            {"user_id": ObjectId(user_id), "name": "dropbox", "connected_account": connected_account},
            {"$set": {
                "dropbox_cursor": str(cursor),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )

    # Webhook lookup methods (find user by webhook identifiers)
    async def get_user_by_webhook_resource_id(self, resource_id: str, integration_name: str) -> Optional[str]:
        """Find user by Google webhook resource_id (Calendar/Drive)."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": integration_name, "webhook_info.webhook_resource_id": resource_id},
            projection={"user_id": 1}
        )
        return str(integ["user_id"]) if integ else None

    async def get_user_and_account_by_webhook_resource_id(self, resource_id: str, integration_name: str) -> Optional[tuple[str, str]]:
        """Find user_id and connected_account by Google webhook resource_id (Calendar/Drive)."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": integration_name, "webhook_info.webhook_resource_id": resource_id},
            projection={"user_id": 1, "connected_account": 1}
        )
        if integ:
            return str(integ["user_id"]), integ.get("connected_account")
        return None

    async def get_user_by_subscription_id(self, subscription_id: str, integration_name: str) -> Optional[str]:
        """Find user by Microsoft Graph subscription_id (Outlook/Calendar/OneDrive)."""
        # Check different metadata fields based on integration type
        metadata_fields = [
            f"metadata.{integration_name}_webhook_subscription_id",
            "metadata.outlook_webhook_subscription_id",
            "metadata.calendar_webhook_subscription_id",
            "metadata.onedrive_webhook_subscription_id"
        ]

        for field in metadata_fields:
            integ = await self.db_manager.db["integrations"].find_one(
                {field: subscription_id},
                projection={"user_id": 1}
            )
            if integ:
                return str(integ["user_id"])
        return None

    async def get_user_by_trello_board_id(self, board_id: str) -> Optional[str]:
        """Find user by Trello board_id."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": "trello", "metadata.webhook_info.webhooks.board_id": board_id},
            projection={"user_id": 1}
        )
        return str(integ["user_id"]) if integ else None

    async def get_user_by_dropbox_account_id(self, account_id: str) -> Optional[tuple[str, str]]:
        """Find user by Dropbox account_id. Returns (user_id, connected_account) tuple."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": "dropbox", "metadata.webhook_info.account_id": account_id},
            projection={"user_id": 1, "connected_account": 1}
        )
        if integ:
            return (str(integ["user_id"]), integ.get("connected_account"))
        return None

    async def get_user_by_notion_bot_id(self, bot_id: str) -> Optional[str]:
        """Find user by Notion bot_id."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": "notion", "metadata.webhook_info.bot_id": bot_id},
            projection={"user_id": 1}
        )
        return str(integ["user_id"]) if integ else None

    async def get_user_by_slack_team_id(self, team_id: str) -> Optional[str]:
        """Find user by Slack team_id."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": "slack", "metadata.webhook_info.team_id": team_id},
            projection={"user_id": 1}
        )
        return str(integ["user_id"]) if integ else None

    async def get_user_by_discord_guild_id(self, guild_id: str) -> Optional[str]:
        """Find user by Discord guild_id (deprecated - use get_user_by_discord_user_id instead)."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": "discord", "connected_account": guild_id},
            projection={"user_id": 1}
        )
        return str(integ["user_id"]) if integ else None

    async def get_user_by_discord_user_id(self, discord_user_id: str) -> Optional[str]:
        """Find Praxos user by their Discord user ID."""
        # Discord user ID is stored in metadata.webhook_info.user_id
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": "discord", "metadata.webhook_info.user_id": discord_user_id},
            projection={"user_id": 1}
        )
        return str(integ["user_id"]) if integ else None
    async def get_user_by_ms_id(self, ms_id: str) -> Optional[str]:
        """Find Praxos user by their Microsoft (Outlook) user ID."""
        integ = await self.db_manager.db["integrations"].find_one(
            {"name": "outlook", "metadata.provider_user_info.id": ms_id},
            projection={"user_id": 1}
        )
        return str(integ["user_id"]) if integ else None
    async def get_all_integrations_for_user_by_name(self, user_id: str, name: str) -> List[Dict[str, Any]]:
        """Get all integrations for a user by name."""
        integrations = await self.db_manager.db["integrations"].find({"user_id": ObjectId(user_id), "name": name}).to_list(length=100)
        return integrations

    async def get_user_integration_names(self, user_id: str) -> List[str]:
        """Get all integration names for a user."""
        integrations = await self.db_manager.db["integrations"].find({"user_id": ObjectId(user_id)}).to_list(length=100)
        return set(integration.get("name") for integration in integrations)

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

    async def sync_integration_to_kg(self, user_id: str, integration_name: str, integration_data: Dict[str, Any], praxos_client=None):
        """
        Sync integration state to the knowledge graph.
        Creates or updates a schema:Integration entity in the KG.

        Args:
            user_id: User ID
            integration_name: Name of the integration (e.g., "gmail", "slack")
            integration_data: Integration metadata (status, connected_account, capabilities, etc.)
            praxos_client: Optional PraxosClient instance (created if not provided)
        """
        try:
            # Import here to avoid circular dependency
            if not praxos_client:
                from src.core.praxos_client import PraxosClient
                praxos_client = PraxosClient(
                    environment_name=f"user_{user_id}",
                    api_key=settings.PRAXOS_API_KEY
                )

            # Check if integration entity already exists in KG
            existing = await praxos_client.get_nodes_by_type(
                type_name="schema:Integration",
                include_literals=True,
                max_results=100
            )

            # Look for matching integration
            integration_node = None
            if isinstance(existing, list):
                for node in existing:
                    data = node.get('data', {})
                    props = data.get('properties', {})
                    if props.get('integration_type') == integration_name:
                        integration_node = node
                        break

            # Build properties for the integration entity
            properties = [
                {"key": "integration_type", "value": integration_name, "type": "StringType"},
                {"key": "status", "value": integration_data.get('status', 'active'), "type": "StatusEnumType"},
                {"key": "connected_at", "value": integration_data.get('created_at', datetime.now(timezone.utc)).isoformat(), "type": "DateTimeType"}
            ]

            # Add optional properties
            if integration_data.get('connected_account'):
                properties.append({
                    "key": "account",
                    "value": integration_data['connected_account'],
                    "type": "EmailType" if '@' in str(integration_data['connected_account']) else "StringType"
                })

            # Add capabilities if defined
            if integration_name in self.integration_capabilities:
                properties.append({
                    "key": "capabilities",
                    "value": json.dumps(self.integration_capabilities[integration_name]),
                    "type": "StringType"
                })

            if integration_node:
                # Update existing integration
                node_id = integration_node.get('id') or integration_node.get('data', {}).get('node_id')
                logger.info(f"Updating existing integration in KG: {integration_name} (node_id={node_id})")

                result = await praxos_client.update_entity_properties(
                    node_id=node_id,
                    properties=properties,
                    replace_all=False  # Merge with existing
                )
            else:
                # Create new integration entity
                logger.info(f"Creating new integration in KG: {integration_name}")

                result = await praxos_client.create_entity_in_kg(
                    entity_type="schema:Integration",
                    label=f"{integration_name.title()} Integration",
                    properties=properties
                )

            logger.info(f"Successfully synced {integration_name} integration to KG for user {user_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to sync integration {integration_name} to KG for user {user_id}: {e}", exc_info=True)
            return {"error": str(e)}

    async def remove_integration_from_kg(self, user_id: str, integration_name: str, praxos_client=None):
        """
        Remove integration entity from KG when user disconnects.

        Args:
            user_id: User ID
            integration_name: Name of the integration to remove
            praxos_client: Optional PraxosClient instance
        """
        try:
            if not praxos_client:
                from src.core.praxos_client import PraxosClient
                praxos_client = PraxosClient(
                    environment_name=f"user_{user_id}",
                    api_key=settings.PRAXOS_API_KEY
                )

            # Find the integration entity
            existing = await praxos_client.get_nodes_by_type(
                type_name="schema:Integration",
                include_literals=True,
                max_results=100
            )

            # Look for matching integration
            for node in existing if isinstance(existing, list) else []:
                data = node.get('data', {})
                props = data.get('properties', {})
                if props.get('integration_type') == integration_name:
                    node_id = node.get('id') or data.get('node_id')

                    # Soft delete the integration
                    result = await praxos_client.delete_node_from_kg(
                        node_id=node_id,
                        cascade=True,  # Delete connected properties
                        force=False
                    )

                    logger.info(f"Successfully removed {integration_name} integration from KG for user {user_id}")
                    return result

            logger.warning(f"Integration {integration_name} not found in KG for user {user_id}")
            return {"warning": "Integration not found in KG"}

        except Exception as e:
            logger.error(f"Failed to remove integration {integration_name} from KG for user {user_id}: {e}", exc_info=True)
            return {"error": str(e)}

# Global instance
integration_service = IntegrationService()
