import asyncio
from typing import Optional, Dict, List, Tuple, Any
import httpx
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from datetime import datetime, timedelta

logger = setup_logger(__name__)

class DiscordIntegration(BaseIntegration):
    """Discord integration client for sending/receiving messages with multi-server support."""

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.tokens: Dict[str, str] = {}  # guild_id -> bot_token
        self.connected_accounts: List[str] = []  # guild_ids
        self.guild_info: Dict[str, Dict] = {}  # Store guild metadata
        self.api_base_url = "https://discord.com/api/v10"

    async def authenticate(self) -> bool:
        """
        Authenticates all connected Discord guilds for the user.
        Each guild gets its own bot token.
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
        guild_id = integration_record.get('connected_account')  # guild_id or identifier
        integration_id = integration_record.get('_id')

        try:
            token_info = await integration_service.get_integration_token(
                self.user_id, 'discord', integration_id=integration_id
            )

            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve token for Discord guild {guild_id}")
                return False

            bot_token = token_info['access_token']

            # Test authentication and get bot info
            try:
                async with httpx.AsyncClient() as client:
                    # Get bot user info
                    user_response = await client.get(
                        f"{self.api_base_url}/users/@me",
                        headers={"Authorization": f"Bot {bot_token}"},
                        timeout=30.0
                    )

                    if user_response.status_code != 200:
                        logger.error(f"Failed to authenticate Discord bot for guild {guild_id}")
                        return False

                    bot_user = user_response.json()

                    # Try to get guild info if guild_id is available
                    guild_name = guild_id
                    if guild_id and guild_id.isdigit():
                        try:
                            guild_response = await client.get(
                                f"{self.api_base_url}/guilds/{guild_id}",
                                headers={"Authorization": f"Bot {bot_token}"},
                                timeout=30.0
                            )
                            if guild_response.status_code == 200:
                                guild_data = guild_response.json()
                                guild_name = guild_data.get("name", guild_id)
                        except Exception:
                            pass  # Guild info is optional

                    # Store token and guild info
                    self.tokens[guild_id] = bot_token
                    self.guild_info[guild_id] = {
                        "guild_id": guild_id,
                        "guild_name": guild_name,
                        "bot_user_id": bot_user.get("id"),
                        "bot_username": bot_user.get("username")
                    }

                    if guild_id not in self.connected_accounts:
                        self.connected_accounts.append(guild_id)

                    logger.info(f"Successfully authenticated Discord guild: {guild_name} ({guild_id})")
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

    def _get_client_for_account(self, account: Optional[str] = None) -> Tuple[discord.Client, str]:
        """
        Retrieves the Discord client and resolved guild identifier.
        Handles default logic for single-guild users.
        """
        if account:
            client = self.clients.get(account)
            if not client:
                raise ValueError(
                    f"Guild '{account}' is not authenticated. "
                    f"Available guilds: {self.connected_accounts}"
                )
            return client, account

        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.clients[default_account], default_account

        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Discord guilds found for this user.")

        raise ValueError(
            f"Multiple Discord guilds exist. Specify which guild to use with "
            f"the 'account' parameter. Available guilds: {self.connected_accounts}"
        )

    async def send_message(self, channel_id: int, text: str, *, embed: discord.Embed = None, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a message to a Discord channel.

        Args:
            channel_id: Channel ID (as integer)
            text: Message text
            embed: Optional rich embed
            account: Optional Discord guild identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Sending Discord message to {channel_id} in guild {resolved_account}")

        try:
            # Ensure bot is ready
            await client.wait_until_ready()

            channel = client.get_channel(channel_id)
            if not channel:
                raise Exception(f"Channel {channel_id} not found or bot doesn't have access")

            # Send message
            message = await channel.send(content=text if text else None, embed=embed)

            return {
                "status": "success",
                "message_id": message.id,
                "channel_id": message.channel.id,
                "created_at": message.created_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Discord error sending message: {e}")
            raise Exception(f"Failed to send Discord message: {str(e)}")

    async def send_dm(self, user_id: int, text: str, *, embed: discord.Embed = None, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a direct message to a Discord user.

        Args:
            user_id: Discord user ID (as integer)
            text: Message text
            embed: Optional rich embed
            account: Optional Discord guild identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Sending Discord DM to user {user_id} in guild {resolved_account}")

        try:
            # Ensure bot is ready
            await client.wait_until_ready()

            user = await client.fetch_user(user_id)
            if not user:
                raise Exception(f"User {user_id} not found")

            # Send DM
            message = await user.send(content=text if text else None, embed=embed)

            return {
                "status": "success",
                "message_id": message.id,
                "user_id": user.id,
                "created_at": message.created_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Discord error sending DM: {e}")
            raise Exception(f"Failed to send Discord DM: {str(e)}")

    async def get_channel_history(self, channel_id: int, *, limit: int = 100, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch message history from a Discord channel.

        Args:
            channel_id: Channel ID (as integer)
            limit: Maximum number of messages to fetch
            account: Optional Discord guild identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Fetching channel history for {channel_id} in guild {resolved_account}")

        try:
            # Ensure bot is ready
            await client.wait_until_ready()

            channel = client.get_channel(channel_id)
            if not channel:
                raise Exception(f"Channel {channel_id} not found or bot doesn't have access")

            # Fetch messages
            messages = []
            async for message in channel.history(limit=limit):
                messages.append({
                    "content": message.content,
                    "author_id": message.author.id,
                    "author_name": message.author.name,
                    "message_id": message.id,
                    "timestamp": message.created_at.isoformat(),
                    "edited_at": message.edited_at.isoformat() if message.edited_at else None,
                    "attachments": [att.url for att in message.attachments],
                    "embeds": len(message.embeds),
                    "type": str(message.type)
                })

            return messages

        except Exception as e:
            logger.error(f"Discord error fetching channel history: {e}")
            return []

    async def list_channels(self, guild_id: Optional[int] = None, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all channels in a Discord guild.

        Args:
            guild_id: Optional guild ID to list channels from (uses account if not provided)
            account: Optional Discord guild identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Listing Discord channels in guild {resolved_account}")

        try:
            # Ensure bot is ready
            await client.wait_until_ready()

            # Get guild
            if guild_id:
                guild = client.get_guild(guild_id)
            else:
                # Get guild from resolved_account
                guild = client.get_guild(int(resolved_account))

            if not guild:
                raise Exception(f"Guild not found or bot is not a member")

            # List channels
            formatted_channels = []
            for channel in guild.channels:
                channel_info = {
                    "id": channel.id,
                    "name": channel.name,
                    "type": str(channel.type),
                    "position": channel.position,
                }

                # Add additional info for text channels
                if isinstance(channel, discord.TextChannel):
                    channel_info["topic"] = channel.topic
                    channel_info["nsfw"] = channel.nsfw

                formatted_channels.append(channel_info)

            return formatted_channels

        except Exception as e:
            logger.error(f"Discord error listing channels: {e}")
            return []

    async def list_guilds(self, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all guilds the bot is a member of.

        Args:
            account: Optional Discord guild identifier (lists all if not provided)
        """
        if account:
            client, resolved_account = self._get_client_for_account(account)
            clients_to_check = [(client, resolved_account)]
        else:
            # List all guilds from all clients
            clients_to_check = [(self.clients[acc], acc) for acc in self.connected_accounts]

        logger.info(f"Listing Discord guilds")

        all_guilds = []

        for client, resolved_account in clients_to_check:
            try:
                # Ensure bot is ready
                await client.wait_until_ready()

                for guild in client.guilds:
                    all_guilds.append({
                        "id": guild.id,
                        "name": guild.name,
                        "member_count": guild.member_count,
                        "owner_id": guild.owner_id,
                        "created_at": guild.created_at.isoformat(),
                        "description": guild.description,
                        "account": resolved_account
                    })

            except Exception as e:
                logger.error(f"Discord error listing guilds for account {resolved_account}: {e}")
                continue

        return all_guilds

    async def get_guild_info(self, guild_id: int, *, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about a Discord guild.

        Args:
            guild_id: Guild ID (as integer)
            account: Optional Discord guild identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        try:
            # Ensure bot is ready
            await client.wait_until_ready()

            guild = client.get_guild(guild_id)
            if not guild:
                raise Exception(f"Guild {guild_id} not found or bot is not a member")

            return {
                "id": guild.id,
                "name": guild.name,
                "description": guild.description,
                "owner_id": guild.owner_id,
                "member_count": guild.member_count,
                "created_at": guild.created_at.isoformat(),
                "icon_url": str(guild.icon.url) if guild.icon else None,
                "banner_url": str(guild.banner.url) if guild.banner else None,
                "roles_count": len(guild.roles),
                "channels_count": len(guild.channels),
                "text_channels_count": len(guild.text_channels),
                "voice_channels_count": len(guild.voice_channels),
                "account": resolved_account
            }

        except Exception as e:
            logger.error(f"Discord error getting guild info: {e}")
            return {}

    async def get_user_info(self, user_id: int, *, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about a Discord user.

        Args:
            user_id: Discord user ID (as integer)
            account: Optional Discord guild identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        try:
            # Ensure bot is ready
            await client.wait_until_ready()

            user = await client.fetch_user(user_id)
            if not user:
                raise Exception(f"User {user_id} not found")

            return {
                "id": user.id,
                "name": user.name,
                "discriminator": user.discriminator,
                "display_name": user.display_name,
                "bot": user.bot,
                "created_at": user.created_at.isoformat(),
                "avatar_url": str(user.avatar.url) if user.avatar else None,
                "account": resolved_account
            }

        except Exception as e:
            logger.error(f"Discord error getting user info: {e}")
            return {}

    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent messages from channels the bot has access to."""
        client, resolved_account = self._get_client_for_account(account)

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        logger.info(f"Fetching recent Discord messages for guild {resolved_account} since {since}")

        try:
            # Ensure bot is ready
            await client.wait_until_ready()

            recent_messages = []

            # Get guilds
            for guild in client.guilds:
                # Iterate through text channels
                for channel in guild.text_channels:
                    try:
                        # Fetch recent messages from this channel
                        messages = await self.get_channel_history(
                            channel_id=channel.id,
                            limit=50,
                            account=resolved_account
                        )

                        # Filter by timestamp
                        for msg in messages:
                            msg_time = datetime.fromisoformat(msg.get("timestamp"))
                            if msg_time >= since:
                                msg["channel_id"] = channel.id
                                msg["channel_name"] = channel.name
                                msg["guild_id"] = guild.id
                                msg["guild_name"] = guild.name
                                msg["account"] = resolved_account
                                recent_messages.append(msg)

                    except Exception as e:
                        logger.warning(f"Could not fetch messages from channel {channel.name}: {e}")
                        continue

            return recent_messages

        except Exception as e:
            logger.error(f"Error fetching recent Discord data for guild {resolved_account}: {e}")
            return []

    async def cleanup(self):
        """Close all Discord client connections."""
        logger.info(f"Cleaning up Discord clients for user {self.user_id}")
        for guild_id, client in self.clients.items():
            try:
                await client.close()
                logger.info(f"Closed Discord client for guild {guild_id}")
            except Exception as e:
                logger.error(f"Error closing Discord client for guild {guild_id}: {e}")
