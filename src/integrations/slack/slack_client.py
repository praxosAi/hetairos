import asyncio
from typing import Optional, Dict, List, Tuple, Any
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger
from datetime import datetime, timedelta

logger = setup_logger(__name__)

class SlackIntegration(BaseIntegration):
    """Slack integration client for sending/receiving messages with multi-workspace support."""

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.clients: Dict[str, AsyncWebClient] = {}
        self.connected_accounts: List[str] = []  # team_id or workspace identifier
        self.team_info: Dict[str, Dict] = {}  # Store team metadata

    async def authenticate(self) -> bool:
        """
        Authenticates all connected Slack workspaces for the user.
        Each workspace gets its own AsyncWebClient instance.
        """
        logger.info(f"Authenticating all Slack workspaces for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(
            self.user_id, 'slack'
        )

        if not integration_records:
            logger.warning(f"No Slack integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record
        ]

        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict) -> bool:
        """Authenticates a single Slack workspace and stores its client."""
        workspace_id = integration_record.get('connected_account')  # team_id or identifier
        integration_id = integration_record.get('_id')

        try:
            token_info = await integration_service.get_integration_token(
                self.user_id, 'slack', integration_id=integration_id
            )

            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve token for Slack workspace {workspace_id}")
                return False

            # Create Slack client for this workspace
            client = AsyncWebClient(token=token_info['access_token'])

            # Test authentication and get workspace info
            try:
                auth_test = await client.auth_test()
                team_id = auth_test.get("team_id")
                team_name = auth_test.get("team")

                # Store client and workspace
                self.clients[workspace_id] = client
                self.team_info[workspace_id] = {
                    "team_id": team_id,
                    "team_name": team_name,
                    "user_id": auth_test.get("user_id"),
                    "bot_id": auth_test.get("bot_id")
                }

                if workspace_id not in self.connected_accounts:
                    self.connected_accounts.append(workspace_id)

                logger.info(f"Successfully authenticated Slack workspace: {team_name} ({team_id})")
                return True

            except SlackApiError as e:
                logger.error(f"Slack API error authenticating workspace {workspace_id}: {e}")
                return False

        except Exception as e:
            logger.error(f"Slack authentication failed for workspace {workspace_id}: {e}")
            return False

    def get_connected_accounts(self) -> List[str]:
        """Returns a list of successfully authenticated Slack workspaces."""
        return self.connected_accounts

    def _get_client_for_account(self, account: Optional[str] = None) -> Tuple[AsyncWebClient, str]:
        """
        Retrieves the Slack client and resolved workspace identifier.
        Handles default logic for single-workspace users.
        """
        if account:
            client = self.clients.get(account)
            if not client:
                raise ValueError(
                    f"Workspace '{account}' is not authenticated. "
                    f"Available workspaces: {self.connected_accounts}"
                )
            return client, account

        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.clients[default_account], default_account

        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Slack workspaces found for this user.")

        raise ValueError(
            f"Multiple Slack workspaces exist. Specify which workspace to use with "
            f"the 'account' parameter. Available workspaces: {self.connected_accounts}"
        )

    async def send_message(self, channel: str, text: str, *, blocks: List[Dict] = None, thread_ts: str = None, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a message to a Slack channel or DM.

        Args:
            channel: Channel ID or user ID for DM
            text: Message text (fallback if blocks are used)
            blocks: Optional rich formatting blocks
            thread_ts: Optional thread timestamp to reply in thread
            account: Optional Slack workspace identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Sending Slack message to {channel} in workspace {resolved_account}")

        try:
            response = await client.chat_postMessage(
                channel=channel,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts
            )

            return {
                "status": "success",
                "message_ts": response.get("ts"),
                "channel": response.get("channel")
            }

        except SlackApiError as e:
            logger.error(f"Slack API error sending message: {e}")
            raise Exception(f"Failed to send Slack message: {e.response['error']}")

    async def send_dm(self, user_id: str, text: str, *, blocks: List[Dict] = None, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a direct message to a Slack user.

        Args:
            user_id: Slack user ID
            text: Message text
            blocks: Optional rich formatting blocks
            account: Optional Slack workspace identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Sending Slack DM to user {user_id} in workspace {resolved_account}")

        try:
            # Open a DM conversation with the user
            dm_response = await client.conversations_open(users=[user_id])
            channel_id = dm_response.get("channel", {}).get("id")

            if not channel_id:
                raise Exception("Failed to open DM conversation")

            # Send the message
            return await self.send_message(
                channel=channel_id,
                text=text,
                blocks=blocks,
                account=resolved_account
            )

        except SlackApiError as e:
            logger.error(f"Slack API error sending DM: {e}")
            raise Exception(f"Failed to send Slack DM: {e.response['error']}")

    async def get_channel_history(self, channel: str, *, limit: int = 100, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch message history from a Slack channel.

        Args:
            channel: Channel ID
            limit: Maximum number of messages to fetch
            account: Optional Slack workspace identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Fetching channel history for {channel} in workspace {resolved_account}")

        try:
            response = await client.conversations_history(
                channel=channel,
                limit=limit
            )

            messages = response.get("messages", [])

            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "text": msg.get("text", ""),
                    "user": msg.get("user"),
                    "ts": msg.get("ts"),
                    "timestamp": datetime.fromtimestamp(float(msg.get("ts", 0))).isoformat() if msg.get("ts") else None,
                    "thread_ts": msg.get("thread_ts"),
                    "type": msg.get("type"),
                    "subtype": msg.get("subtype")
                })

            return formatted_messages

        except SlackApiError as e:
            logger.error(f"Slack API error fetching channel history: {e}")
            return []

    async def list_channels(self, *, types: str = "public_channel,private_channel", account: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all channels in the Slack workspace.

        Args:
            types: Comma-separated channel types (public_channel, private_channel, im, mpim)
            account: Optional Slack workspace identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        logger.info(f"Listing Slack channels in workspace {resolved_account}")

        try:
            response = await client.conversations_list(types=types)

            channels = response.get("channels", [])

            formatted_channels = []
            for channel in channels:
                formatted_channels.append({
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "is_private": channel.get("is_private", False),
                    "is_member": channel.get("is_member", False),
                    "num_members": channel.get("num_members", 0)
                })

            return formatted_channels

        except SlackApiError as e:
            logger.error(f"Slack API error listing channels: {e}")
            return []

    async def get_user_info(self, user_id: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about a Slack user.

        Args:
            user_id: Slack user ID
            account: Optional Slack workspace identifier
        """
        client, resolved_account = self._get_client_for_account(account)

        try:
            response = await client.users_info(user=user_id)

            if not response.get("ok"):
                raise Exception(f"Slack API error: {response.get('error')}")

            user = response.get("user", {})

            return {
                "id": user.get("id"),
                "name": user.get("name"),
                "real_name": user.get("real_name"),
                "email": user.get("profile", {}).get("email"),
                "is_bot": user.get("is_bot", False),
                "timezone": user.get("tz"),
                "workspace": resolved_account
            }

        except SlackApiError as e:
            logger.error(f"Slack API error getting user info: {e}")
            return {}

    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent messages from channels the bot is in."""
        client, resolved_account = self._get_client_for_account(account)

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        logger.info(f"Fetching recent Slack messages for workspace {resolved_account} since {since}")

        try:
            # Get channels bot is member of
            channels_response = await client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True
            )

            recent_messages = []
            for channel in channels_response.get("channels", []):
                if not channel.get("is_member"):
                    continue

                # Fetch recent messages from this channel
                messages = await self.get_channel_history(
                    channel=channel.get("id"),
                    limit=50,
                    account=resolved_account
                )

                # Filter by timestamp
                for msg in messages:
                    msg_time = datetime.fromtimestamp(float(msg.get("ts", 0)))
                    if msg_time >= since:
                        msg["channel_id"] = channel.get("id")
                        msg["channel_name"] = channel.get("name")
                        msg["workspace"] = resolved_account
                        recent_messages.append(msg)

            return recent_messages

        except Exception as e:
            logger.error(f"Error fetching recent Slack data for workspace {resolved_account}: {e}")
            return []
