from langchain_core.tools import tool
from src.integrations.slack.slack_client import SlackIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from typing import Optional, List, Dict, Any
import json

logger = setup_logger(__name__)

def create_slack_tools(slack_integration: SlackIntegration) -> list:
    """Creates Slack related tools with multi-workspace support."""

    @tool
    async def list_slack_workspaces() -> ToolExecutionResponse:
        """
        Lists all connected Slack workspaces for the user.
        Use this first to see which Slack workspaces are available.
        """
        try:
            accounts = slack_integration.get_connected_accounts()
            # Include team names for better UX
            workspaces = []
            for workspace_id in accounts:
                team_info = slack_integration.team_info.get(workspace_id, {})
                workspaces.append({
                    "workspace_id": workspace_id,
                    "team_name": team_info.get("team_name"),
                    "team_id": team_info.get("team_id")
                })
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({"workspaces": workspaces})
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="list_slack_workspaces",
                exception=e,
                integration="Slack"
            )

    @tool
    async def send_slack_message(channel: str, text: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Send a message to a Slack channel.

        Args:
            channel: Channel ID or channel name (e.g., "#general" or "C1234567890")
            text: Message text to send
            account: Optional Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used.
        """
        try:
            result = await slack_integration.send_message(channel, text, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "message": "Message sent successfully",
                    "message_ts": result.get("message_ts"),
                    "channel": result.get("channel")
                })
            )
        except ValueError as e:
            # Multi-account error - user needs to specify which workspace
            return ErrorResponseBuilder.missing_parameter(
                operation="send_slack_message",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
            return ErrorResponseBuilder.from_exception(
                operation="send_slack_message",
                exception=e,
                integration="Slack",
                context={"channel": channel}
            )

    @tool
    async def send_slack_dm(user_id: str, text: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Send a direct message to a Slack user.

        Args:
            user_id: Slack user ID (e.g., "U1234567890")
            text: Message text to send
            account: Optional Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used.
        """
        try:
            result = await slack_integration.send_dm(user_id, text, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "message": "DM sent successfully",
                    "message_ts": result.get("message_ts")
                })
            )
        except ValueError as e:
            # Multi-account error - user needs to specify which workspace
            return ErrorResponseBuilder.missing_parameter(
                operation="send_slack_dm",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error sending Slack DM: {e}")
            return ErrorResponseBuilder.from_exception(
                operation="send_slack_dm",
                exception=e,
                integration="Slack",
                context={"user_id": user_id}
            )

    @tool
    async def list_slack_channels(types: str = "public_channel,private_channel", account: Optional[str] = None) -> ToolExecutionResponse:
        """
        List all channels in the Slack workspace.

        Args:
            types: Comma-separated channel types: "public_channel", "private_channel", "im", "mpim" (default: "public_channel,private_channel")
            account: Optional Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used.
        """
        try:
            channels = await slack_integration.list_channels(types=types, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "channels": channels,
                    "count": len(channels)
                })
            )
        except ValueError as e:
            # Multi-account error
            return ErrorResponseBuilder.missing_parameter(
                operation="list_slack_channels",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error listing Slack channels: {e}")
            return ErrorResponseBuilder.from_exception(
                operation="list_slack_channels",
                exception=e,
                integration="Slack"
            )

    @tool
    async def get_slack_channel_history(channel: str, limit: int = 50, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Get message history from a Slack channel.

        Args:
            channel: Channel ID (e.g., "C1234567890")
            limit: Maximum number of messages to fetch (default: 50, max: 1000)
            account: Optional Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used.
        """
        try:
            messages = await slack_integration.get_channel_history(channel, limit=limit, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({
                    "messages": messages,
                    "count": len(messages)
                })
            )
        except ValueError as e:
            # Multi-account error
            return ErrorResponseBuilder.missing_parameter(
                operation="get_slack_channel_history",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error getting Slack channel history: {e}")
            return ErrorResponseBuilder.from_exception(
                operation="get_slack_channel_history",
                exception=e,
                integration="Slack",
                context={"channel": channel}
            )

    @tool
    async def get_slack_user_info(user_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Get information about a Slack user.

        Args:
            user_id: Slack user ID (e.g., "U1234567890")
            account: Optional Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used.
        """
        try:
            user_info = await slack_integration.get_user_info(user_id, account=account)
            return ToolExecutionResponse(
                status="success",
                result=json.dumps(user_info)
            )
        except ValueError as e:
            # Multi-account error
            return ErrorResponseBuilder.missing_parameter(
                operation="get_slack_user_info",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error getting Slack user info: {e}")
            return ErrorResponseBuilder.from_exception(
                operation="get_slack_user_info",
                exception=e,
                integration="Slack",
                context={"user_id": user_id}
            )

    return [
        list_slack_workspaces,
        send_slack_message,
        send_slack_dm,
        list_slack_channels,
        get_slack_channel_history,
        get_slack_user_info
    ]
