import asyncio
import httpx
import os
from typing import Optional, Dict, List, Tuple, Any
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from datetime import datetime, timedelta

logger = setup_logger(__name__)

class DiscordIntegration(BaseIntegration):
    """
    Discord integration client for sending/receiving messages.

    Uses GLOBAL bot token (like WhatsApp/Telegram) not per-user OAuth tokens.
    OAuth tokens are only used to link Discord users to Praxos users.
    """

    def __init__(self, user_id: str):
        super().__init__(user_id)
        # Global bot token from environment (shared across all users)
        self.bot_token = os.getenv("DISCORD_BOT_TOKEN")
        # Per-user data
        self.user_discord_id: Optional[str] = None  # User's Discord ID
        self.user_guilds: List[str] = []  # Guilds user has access to
        self.api_base = "https://discord.com/api/v10"

    async def authenticate(self) -> bool:
        """
        Authenticates Discord integration by verifying bot token and loading user's Discord info.
        Uses global bot token (not per-user OAuth tokens).
        """
        if not self.bot_token:
            logger.error("DISCORD_BOT_TOKEN not set in environment")
            return False

        logger.info(f"Authenticating Discord for user {self.user_id}")

        # Get user's Discord OAuth data (for linking purposes)
        integration_records = await integration_service.get_all_integrations_for_user_by_name(
            self.user_id, 'discord'
        )

        if not integration_records:
            logger.warning(f"No Discord integrations found for user {self.user_id}")
            return False

        # Get first integration (users typically have one Discord account)
        integration_record = integration_records[0]

        # Extract user's Discord ID from metadata
        self.user_discord_id = integration_record.get('metadata', {}).get('webhook_info', {}).get('user_id')

        if not self.user_discord_id:
            # Fallback: try to get from connected_account
            self.user_discord_id = integration_record.get('connected_account')

        logger.info(f"Discord user ID: {self.user_discord_id}")
        return True

    async def send_message(self, channel: str, text: str, *, embed: Dict = None) -> Dict[str, Any]:
        """
        Send a message to a Discord channel using global bot token.

        Args:
            channel: Channel ID
            text: Message text
            embed: Optional Discord embed object
        """
        if not self.bot_token:
            raise Exception("DISCORD_BOT_TOKEN not set in environment")

        logger.info(f"Sending Discord message to channel {channel}")

        try:
            payload = {"content": text}
            if embed:
                payload["embed"] = embed

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/channels/{channel}/messages",
                    headers={
                        "Authorization": f"Bot {self.bot_token}",
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

    async def send_dm(self, user_id: str, text: str, *, embed: Dict = None) -> Dict[str, Any]:
        """
        Send a direct message to a Discord user using global bot token.

        Args:
            user_id: Discord user ID
            text: Message text
            embed: Optional Discord embed
        """
        if not self.bot_token:
            raise Exception("DISCORD_BOT_TOKEN not set in environment")

        logger.info(f"Sending Discord DM to user {user_id}")

        try:
            # Create DM channel
            async with httpx.AsyncClient() as client:
                dm_response = await client.post(
                    f"{self.api_base}/users/@me/channels",
                    headers={
                        "Authorization": f"Bot {self.bot_token}",
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
                embed=embed
            )

        except Exception as e:
            logger.error(f"Discord API error sending DM: {e}")
            raise Exception(f"Failed to send Discord DM: {e}")

    async def get_channel_history(self, channel: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch message history from a Discord channel using global bot token.

        Args:
            channel: Channel ID
            limit: Maximum number of messages to fetch
        """
        if not self.bot_token:
            raise Exception("DISCORD_BOT_TOKEN not set")

        logger.info(f"Fetching channel history for {channel}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/channels/{channel}/messages",
                    headers={"Authorization": f"Bot {self.bot_token}"},
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

    async def list_channels(self, guild_id: str) -> List[Dict[str, Any]]:
        """
        List all channels in a Discord guild using global bot token.

        Args:
            guild_id: Discord guild ID
        """
        if not self.bot_token:
            raise Exception("DISCORD_BOT_TOKEN not set")

        logger.info(f"Listing Discord channels in guild {guild_id}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/guilds/{guild_id}/channels",
                    headers={"Authorization": f"Bot {self.bot_token}"}
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

    async def fetch_recent_data(self, *, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent messages - not implemented for Discord (use Gateway events)."""
        return []
