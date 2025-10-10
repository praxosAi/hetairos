from langchain_core.tools import tool
from src.integrations.discord.discord_client import DiscordIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from typing import Optional, List, Dict, Any
import json

logger = setup_logger(__name__)

def create_discord_tools(discord_integration: DiscordIntegration) -> list:
    """Creates Discord related tools with multi-server support."""

    @tool
    async def list_discord_servers() -> ToolExecutionResponse:
        """
        Lists all connected Discord servers for the user.
        Use this first to see which Discord servers are available.
        """
        try:
            accounts = discord_integration.get_connected_accounts()
            # Include team names for better UX
            servers = []
            for server_id in accounts:
                team_info = discord_integration.team_info.get(server_id, {})
                servers.append({
                    "server_id": server_id,
                    "team_name": team_info.get("team_name"),
                    "team_id": team_info.get("team_id")
                })
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({"servers": servers})
            )
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def send_discord_message(channel: str, text: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Send a message to a Discord channel.

        Args:
            channel: Channel ID or channel name (e.g., "#general" or "C1234567890")
            text: Message text to send
            account: Optional Discord server identifier. If not specified and user has only one server, that server will be used.
        """
        try:
            result = await discord_integration.send_message(channel, text, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "message": "Message sent successfully",
                    "message_ts": result.get("message_ts"),
                    "channel": result.get("channel")
                })
            )
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            logger.error(f"Error sending Discord message: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Failed to send Discord message")

    @tool
    async def send_discord_dm(user_id: str, text: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Send a direct message to a Discord user.

        Args:
            user_id: Discord user ID (e.g., "U1234567890")
            text: Message text to send
            account: Optional Discord server identifier. If not specified and user has only one server, that server will be used.
        """
        try:
            result = await discord_integration.send_dm(user_id, text, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "message": "DM sent successfully",
                    "message_ts": result.get("message_ts")
                })
            )
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            logger.error(f"Error sending Discord DM: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e), user_message="Failed to send Discord DM")

    @tool
    async def list_discord_channels(types: str = "public_channel,private_channel", account: Optional[str] = None) -> ToolExecutionResponse:
        """
        List all channels in the Discord server.

        Args:
            types: Comma-separated channel types: "public_channel", "private_channel", "im", "mpim" (default: "public_channel,private_channel")
            account: Optional Discord server identifier. If not specified and user has only one server, that server will be used.
        """
        try:
            channels = await discord_integration.list_channels(types=types, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "channels": channels,
                    "count": len(channels)
                })
            )
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            logger.error(f"Error listing Discord channels: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_discord_channel_history(channel: str, limit: int = 50, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Get message history from a Discord channel.

        Args:
            channel: Channel ID (e.g., "C1234567890")
            limit: Maximum number of messages to fetch (default: 50, max: 1000)
            account: Optional Discord server identifier. If not specified and user has only one server, that server will be used.
        """
        try:
            messages = await discord_integration.get_channel_history(channel, limit=limit, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "messages": messages,
                    "count": len(messages)
                })
            )
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            logger.error(f"Error getting Discord channel history: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_discord_user_info(user_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Get information about a Discord user.

        Args:
            user_id: Discord user ID (e.g., "U1234567890")
            account: Optional Discord server identifier. If not specified and user has only one server, that server will be used.
        """
        try:
            user_info = await discord_integration.get_user_info(user_id, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps(user_info)
            )
        except ValueError as e:
            # Multi-account error
            return ToolExecutionResponse(status="error", user_message=str(e))
        except Exception as e:
            logger.error(f"Error getting Discord user info: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e))

    return [
        list_discord_servers,
        send_discord_message,
        send_discord_dm,
        list_discord_channels,
        get_discord_channel_history,
        get_discord_user_info
    ]
