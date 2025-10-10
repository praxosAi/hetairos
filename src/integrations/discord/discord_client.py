import asyncio
import httpx
from typing import Optional, Dict, List, Tuple, Any
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from datetime import datetime, timedelta

logger = setup_logger(__name__)

class DiscordIntegration(BaseIntegration):
    """Discord integration client for sending/receiving messages with multi-guild (server) support."""

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.tokens: Dict[str, str] = {}  # Bot tokens per guild
        self.connected_accounts: List[str] = []  # guild_ids
        self.guild_info: Dict[str, Dict] = {}  # Store guild metadata
        self.api_base = "https://discord.com/api/v10"

    async def authenticate(self) -> bool:
        """
        Authenticates all connected Discord guilds (servers) for the user.
        Each guild gets its own bot token stored.
        """
        logger.info(f"Authenticating all Discord guilds for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(
            self.user_id, 'discord'
        )

        if not integration_records:
            logger.warning(f"No Discord integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record
        ]

        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict) -> bool:
        """Authenticates a single Discord guild and stores its token."""
        guild_id = integration_record.get('connected_account')
        integration_id = integration_record.get('_id')

        try:
            token_info = await integration_service.get_integration_token(
                self.user_id, 'discord', integration_id=integration_id
            )

            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve token for Discord guild {guild_id}")
                return False

            # Store bot token
            bot_token = token_info['access_token']
            self.tokens[guild_id] = bot_token

            # Get guild info using bot token
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.api_base}/users/@me",
                        headers={"Authorization": f"Bot {bot_token}"}
                    )

                    if response.status_code == 200:
                        user_data = response.json()
                        self.guild_info[guild_id] = {
                            "bot_id": user_data.get("id"),
                            "bot_username": user_data.get("username")
                        }

                if guild_id not in self.connected_accounts:
                    self.connected_accounts.append(guild_id)

                logger.info(f"Successfully authenticated Discord guild: {guild_id}")
                return True

            except Exception as e:
                logger.error(f"Discord API error authenticating guild {guild_id}: {e}")
                return False

        except Exception as e:
            logger.error(f"Discord authentication failed for guild {guild_id}: {e}")
            return False

    def get_connected_accounts(self) -> List[str]:
        """Returns a list of successfully authenticated Discord guilds."""
        return self.connected_accounts

    def _get_token_for_account(self, account: Optional[str] = None) -> Tuple[str, str]:
        """
        Retrieves the Discord bot token and resolved guild identifier.
        Handles default logic for single-guild users.
        """
        if account:
            token = self.tokens.get(account)
            if not token:
                raise ValueError(
                    f"Guild '{account}' is not authenticated. "
                    f"Available guilds: {self.connected_accounts}"
                )
            return token, account

        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.tokens[default_account], default_account

        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Discord guilds found for this user.")

        raise ValueError(
            f"Multiple Discord guilds exist. Specify which guild to use with "
            f"the 'account' parameter. Available guilds: {self.connected_accounts}"
        )

    async def send_message(self, channel: str, text: str, *, embed: Dict = None, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a message to a Discord channel.

        Args:
            channel: Channel ID
            text: Message text
            embed: Optional Discord embed object
            account: Optional Discord guild identifier
        """
        token, resolved_account = self._get_token_for_account(account)

        logger.info(f"Sending Discord message to {channel} in guild {resolved_account}")

        try:
            payload = {"content": text}
            if embed:
                payload["embed"] = embed

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/channels/{channel}/messages",
                    headers={
                        "Authorization": f"Bot {token}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )

                if response.status_code not in [200, 201]:
                    raise Exception(f"Discord API error: {response.status_code} - {response.text}")

                data = response.json()
                return {
                    "status": "success",
                    "message_id": data.get("id"),
                    "channel_id": data.get("channel_id")
                }

        except Exception as e:
            logger.error(f"Discord API error sending message: {e}")
            raise Exception(f"Failed to send Discord message: {e}")

    async def send_dm(self, user_id: str, text: str, *, embed: Dict = None, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a direct message to a Discord user.

        Args:
            user_id: Discord user ID
            text: Message text
            embed: Optional Discord embed
            account: Optional Discord guild identifier
        """
        token, resolved_account = self._get_token_for_account(account)

        logger.info(f"Sending Discord DM to user {user_id}")

        try:
            # Create DM channel
            async with httpx.AsyncClient() as client:
                dm_response = await client.post(
                    f"{self.api_base}/users/@me/channels",
                    headers={
                        "Authorization": f"Bot {token}",
                        "Content-Type": "application/json"
                    },
                    json={"recipient_id": user_id}
                )

                if dm_response.status_code not in [200, 201]:
                    raise Exception(f"Failed to create DM channel: {dm_response.status_code}")

                dm_data = dm_response.json()
                channel_id = dm_data.get("id")

            # Send message to DM channel
            return await self.send_message(
                channel=channel_id,
                text=text,
                embed=embed,
                account=resolved_account
            )

        except Exception as e:
            logger.error(f"Discord API error sending DM: {e}")
            raise Exception(f"Failed to send Discord DM: {e}")

    async def get_channel_history(self, channel: str, *, limit: int = 100, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch message history from a Discord channel.

        Args:
            channel: Channel ID
            limit: Maximum number of messages to fetch
            account: Optional Discord guild identifier
        """
        token, resolved_account = self._get_token_for_account(account)

        logger.info(f"Fetching channel history for {channel} in guild {resolved_account}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/channels/{channel}/messages",
                    headers={"Authorization": f"Bot {token}"},
                    params={"limit": limit}
                )

                if response.status_code != 200:
                    logger.error(f"Discord API error: {response.status_code}")
                    return []

                messages = response.json()

            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "text": msg.get("content", ""),
                    "user": msg.get("author", {}).get("id"),
                    "username": msg.get("author", {}).get("username"),
                    "id": msg.get("id"),
                    "timestamp": msg.get("timestamp"),
                    "channel_id": msg.get("channel_id"),
                    "type": msg.get("type")
                })

            return formatted_messages

        except Exception as e:
            logger.error(f"Discord API error fetching channel history: {e}")
            return []

    async def list_channels(self, guild_id: str, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all channels in a Discord guild (server).

        Args:
            guild_id: Discord guild ID
            account: Optional Discord guild identifier
        """
        token, resolved_account = self._get_token_for_account(account)

        logger.info(f"Listing Discord channels in guild {guild_id}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/guilds/{guild_id}/channels",
                    headers={"Authorization": f"Bot {token}"}
                )

                if response.status_code != 200:
                    logger.error(f"Discord API error: {response.status_code}")
                    return []

                channels = response.json()

            formatted_channels = []
            for channel in channels:
                formatted_channels.append({
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "type": channel.get("type"),  # 0=text, 2=voice, 4=category, etc.
                    "position": channel.get("position")
                })

            return formatted_channels

        except Exception as e:
            logger.error(f"Discord API error listing channels: {e}")
            return []

    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent messages from Discord guild."""
        token, resolved_account = self._get_token_for_account(account)

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        logger.info(f"Fetching recent Discord messages for guild {resolved_account} since {since}")

        # Note: Discord doesn't provide easy "all messages" API
        # This is a simplified version - in production you'd use Gateway events
        return []
