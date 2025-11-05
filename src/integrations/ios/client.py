from typing import Optional
from urllib.parse import urlencode
from src.integrations.imessage.client import IMessageClient
from src.utils.logging import setup_logger
from src.services.integration_service import integration_service


class IOSClient:
    """
    Client for sending commands to iOS Shortcuts via iMessage.

    Commands are encoded as URL parameters and sent as text messages.
    iOS Shortcuts automation watches for messages with the command format
    and executes them.
    """

    def __init__(self):
        self.logger = setup_logger("ios_client")
        self.imessage_client = IMessageClient()

    async def send_command(
        self,
        user_id: str,
        command_type: str,
        params: dict
    ) -> Optional[dict]:
        """
        Send a command to the user's iOS device.

        Args:
            user_id: The Praxos user ID
            command_type: Type of command (e.g., "sendMessage", "executeAction")
            params: Additional parameters for the command

        Returns:
            Response from iMessage send operation

        Example:
            await ios_client.send_command(
                user_id="123",
                command_type="sendMessage",
                params={"msg": "Hello!", "target": "+19292717338"}
            )
            # Sends: type=PraxosCommand&command=sendMessage&msg=Hello!&target=+19292717338
        """
        # Look up user's phone number from integration
        integrations = await integration_service.get_user_integrations(user_id)
        ios_integration = next((i for i in integrations if i.get("name") == "ios"), None)

        if not ios_integration or not ios_integration.get("ios_user_phone"):
            self.logger.error(f"No iOS integration or phone number found for user {user_id}")
            return None

        user_phone = ios_integration["ios_user_phone"]

        # Build command parameters
        command_params = {
            "type": "PraxosCommand",
            "command": command_type,
            **params
        }

        # URL-encode the command
        command_string = urlencode(command_params)

        self.logger.info(f"Sending iOS command to {user_phone}: {command_string}")

        # Send via iMessage
        try:
            result = await self.imessage_client.send_message(user_phone, command_string)
            self.logger.info(f"iOS command sent successfully to {user_phone}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to send iOS command to {user_phone}: {e}", exc_info=True)
            return None

    async def send_text_message(
        self,
        user_id: str,
        message: str,
        target_phone: str
    ) -> Optional[dict]:
        """
        Send a text message via iOS Shortcuts.

        Args:
            user_id: The Praxos user ID
            message: The message content
            target_phone: Phone number to send to

        Returns:
            Response from command send operation
        """
        return await self.send_command(
            user_id=user_id,
            command_type="sendMessage",
            params={
                "msg": message,
                "target": target_phone
            }
        )

    async def execute_shortcut(
        self,
        user_id: str,
        shortcut_name: str,
        input_text: Optional[str] = None
    ) -> Optional[dict]:
        """
        Trigger a specific iOS Shortcut by name.

        Args:
            user_id: The Praxos user ID
            shortcut_name: Name of the shortcut to execute
            input_text: Optional input text for the shortcut

        Returns:
            Response from command send operation
        """
        params = {"shortcut": shortcut_name}
        if input_text:
            params["input"] = input_text

        return await self.send_command(
            user_id=user_id,
            command_type="executeShortcut",
            params=params
        )

    async def set_reminder(
        self,
        user_id: str,
        title: str,
        due_date: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[dict]:
        """
        Create a reminder on the user's iOS device.

        Args:
            user_id: The Praxos user ID
            title: Reminder title
            due_date: Optional due date (ISO format)
            notes: Optional reminder notes

        Returns:
            Response from command send operation
        """
        params = {"title": title}
        if due_date:
            params["dueDate"] = due_date
        if notes:
            params["notes"] = notes

        return await self.send_command(
            user_id=user_id,
            command_type="setReminder",
            params=params
        )
    async def fetch_recent_data(self):
        return
