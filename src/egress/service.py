import logging
import asyncio
from typing import Dict, Optional
from src.config.settings import settings
from src.utils.redis_client import publish_message
from src.integrations.whatsapp.client import WhatsAppClient
from src.integrations.telegram.client import TelegramClient
from src.integrations.imessage.client import IMessageClient
from src.integrations.email.email_bot_client import send_unauthorised_user_bot_reply, send_bot_reply, send_new_email_bot
from src.utils.logging import setup_logger
from src.services.integration_service import integration_service
from src.services.user_service import user_service
logger = setup_logger(__name__)

class EgressService:
    def __init__(self):
        self.whatsapp_client = WhatsAppClient()
        self.telegram_client = TelegramClient()
        self.imessage_client = IMessageClient()
        # Note: Slack client will be initialized per-request with user_id
        # since it requires authentication (unlike WhatsApp/Telegram which use API keys)

        # Track active watchdog tasks per chat/user
        self.active_typing_tasks: Dict[str, asyncio.Task] = {}

    async def start_typing_indicator(self, event: dict) -> Optional[str]:
        """
        Start activity indicator for a user/chat.
        Returns a unique task_id for later stopping.
        """
        try:
            platform = event.get("source")

            if platform == "telegram":
                task_id = await self._start_telegram_typing(event)
                return task_id
            elif platform == "imessage":
                task_id = await self._start_imessage_typing(event)
                return task_id

            return None  # Platform not supported
        except Exception as e:
            logger.error(f"Error starting activity indicator: {e}", exc_info=True)
            return None

    async def stop_typing_indicator(self, task_id: Optional[str]) -> None:
        """
        Stop the activity indicator watchdog by task_id.
        """
        if not task_id:
            return

        await self._cleanup_task(task_id)

    async def _cleanup_task(self, task_id: str) -> None:
        """
        Cancel and cleanup a specific watchdog task.
        """
        task = self.active_typing_tasks.get(task_id)

        if not task:
            logger.debug(f"Task {task_id} not found (already cleaned up?)")
            return

        if task.done():
            # Already finished (crashed or completed)
            del self.active_typing_tasks[task_id]
            return

        # Cancel the task
        task.cancel()

        try:
            # Wait for cancellation to complete
            await task
        except asyncio.CancelledError:
            # Expected - task was cancelled successfully
            pass
        except Exception as e:
            logger.error(f"Error cleaning up task {task_id}: {e}")
        finally:
            # Remove from tracking dict
            if task_id in self.active_typing_tasks:
                del self.active_typing_tasks[task_id]

    async def _telegram_typing_watchdog(self, chat_id: int) -> None:
        """
        Continuously sends typing action every 4 seconds until cancelled.
        Telegram typing status lasts ~5 seconds, so we refresh at 4s intervals.
        """
        try:
            for sending_counter in range(30):  # Limit to 30 sends (2 minutes) to avoid infinite loops
                try:
                    # Send typing action
                    await self.telegram_client.send_typing_action(chat_id)
                except Exception as e:
                    # Don't crash on API errors, just log and continue
                    logger.warning(f"Failed to send typing action to chat {chat_id}: {e}")

                # Wait 4 seconds before next update (or until cancelled)
                await asyncio.sleep(4)

        except asyncio.CancelledError:
            # Normal cancellation when processing completes
            logger.debug(f"Typing watchdog cancelled for chat {chat_id}")
            # Don't re-raise, allows graceful cleanup
        except Exception as e:
            logger.error(f"Unexpected error in typing watchdog for chat {chat_id}: {e}")

    async def _imessage_typing_watchdog(self, phone_number: str) -> None:
        """
        Continuously sends typing indicator every 10 seconds until cancelled.
        SendBlue iMessage typing indicator needs periodic refresh.
        """
        try:
            for sending_counter in range(12):  # Limit to 12 sends (2 minutes) to avoid infinite loops
                try:
                    logger.info("Sending iMessage typing indicator to %s", phone_number)
                    # Send typing indicator
                    await self.imessage_client.set_typing_indicator(phone_number)
                except Exception as e:
                    # Don't crash on API errors, just log and continue
                    logger.warning(f"Failed to send typing indicator to iMessage {phone_number}: {e}")

                # Wait 10 seconds before next update (or until cancelled)
                await asyncio.sleep(10)

        except asyncio.CancelledError:
            # Normal cancellation when processing completes
            logger.debug(f"Typing watchdog cancelled for iMessage {phone_number}")
            # Don't re-raise, allows graceful cleanup
        except Exception as e:
            logger.error(f"Unexpected error in typing watchdog for iMessage {phone_number}: {e}")

    async def _start_telegram_typing(self, event: dict) -> Optional[str]:
        """
        Start Telegram typing watchdog and register it.
        Returns task_id for later cancellation.
        """
        # Extract chat_id
        chat_id = event.get("output_chat_id")
        if not chat_id:
            try:
                integration_record = await integration_service.get_integration_record_for_user_and_name(
                    user_id=event.get("user_id"),
                    name="telegram"
                )
                if integration_record:
                    chat_id = integration_record.get("telegram_chat_id")
            except Exception as e:
                logger.error(f"Failed to get chat_id for typing indicator: {e}")
                return None

        if not chat_id:
            logger.warning("No chat_id found, cannot start typing indicator")
            return None

        # Create unique task ID
        task_id = f"telegram:{chat_id}:{event.get('user_id')}"

        # If there's already a watchdog for this chat, cancel it first
        # (handles rapid messages from same user)
        if task_id in self.active_typing_tasks:
            await self._cleanup_task(task_id)

        # Start new watchdog task
        task = asyncio.create_task(self._telegram_typing_watchdog(chat_id))
        self.active_typing_tasks[task_id] = task

        logger.debug(f"Started typing watchdog for {task_id}")
        return task_id

    async def _start_imessage_typing(self, event: dict) -> Optional[str]:
        """
        Start iMessage typing watchdog and register it.
        Returns task_id for later cancellation.
        """
        # Extract phone_number
        phone_number = event.get("output_phone_number")
        if not phone_number:
            try:
                integration_record = await integration_service.get_integration_record_for_user_and_name(
                    user_id=event.get("user_id"),
                    name="imessage"
                )
                if integration_record:
                    phone_number = integration_record.get("connected_account")
            except Exception as e:
                logger.error(f"Failed to get phone_number for typing indicator: {e}")
                return None

        if not phone_number:
            logger.warning("No phone_number found, cannot start typing indicator")
            return None

        # Create unique task ID
        task_id = f"imessage:{phone_number}:{event.get('user_id')}"

        # If there's already a watchdog for this phone, cancel it first
        # (handles rapid messages from same user)
        if task_id in self.active_typing_tasks:
            await self._cleanup_task(task_id)

        # Start new watchdog task
        task = asyncio.create_task(self._imessage_typing_watchdog(phone_number))
        self.active_typing_tasks[task_id] = task

        logger.debug(f"Started typing watchdog for {task_id}")
        return task_id

    async def _send_email_response(self, event: dict, response_text: str):
        if event.get("email_type") == "unauthorised_user":
            await send_unauthorised_user_bot_reply(event.get("original_message"))

        elif event.get("email_type") == "reply":
            await send_bot_reply(event.get('metadata',{}).get("original_message"), response_text)
        elif event.get("email_type") == "new" :
            await send_new_email_bot(event.get('metadata',{}).get("original_message"), event.get("new_email_message"))
        else:
            logger.error(f"Unknown email_type '{event.get('email_type')}' in event metadata. Cannot send email response.")
            

    async def _send_whatsapp_reponse(self, event: dict, response_text, response_files):
        phone_number = event.get("output_phone_number")
        if not phone_number and event.get("user_id"):
            try:
                integration_record = await integration_service.get_integration_record_for_user_and_name(
                    user_id=event.get("user_id"),
                    name="whatsapp"
                )
                if integration_record:
                    phone_number = integration_record.get("connected_account")
                else:
                    logger.error(f"No integration record found for WhatsApp message. Event: {event}")
                    return
                if not phone_number:
                    logger.error(f"No phone_number in integration record for WhatsApp message. Event: {event}")
                    return
            except Exception as e:
                logger.error(f"no phone number found for WhatsApp output type. Event: {event}", exc_info=True)
                return
        if response_text:
            await self.whatsapp_client.send_message(phone_number, response_text)
        if response_files:
            for file_obj in response_files:
                await self.whatsapp_client.send_media_from_link(phone_number, file_obj)
        logger.info(f"Successfully sent response to WhatsApp user {phone_number}")

    async def _send_imessage_response(self, event:dict, response_text, response_files):
        phone_number = event.get("output_phone_number")
        if not phone_number and event.get("user_id"):
            try:
                integration_record = await integration_service.get_integration_record_for_user_and_name(
                    user_id=event.get("user_id"),
                    name="imessage"
                )
                if integration_record:
                    phone_number = integration_record.get("connected_account")
                else:
                    logger.error(f"No integration record found for iMessage message. Event: {event}")
                    return
                if not phone_number:
                    logger.error(f"No phone_number in integration record for iMessage message. Event: {event}")
                    return
            except Exception as e:
                logger.error(f"no phone number found for iMessage output type. Event: {event}", exc_info=True)
                return
        if response_text:
            await self.imessage_client.send_message(phone_number, response_text)
        if response_files:
            for file_obj in response_files:
                await self.imessage_client.send_media(phone_number, file_obj)
        # Note: Sending media via iMessage is not implemented here.
        logger.info(f"Successfully sent response to iMessage user {phone_number}")

    async def _send_telegram_response(self, event, response_text, response_files):
        chat_id = event.get("output_chat_id")
        if not chat_id:
            try:
                integration_record = await integration_service.get_integration_record_for_user_and_name(user_id=event.get("user_id"), name="telegram")
                if integration_record:
                    chat_id = integration_record.get("telegram_chat_id")
                else:
                    logger.error(f"No integration record found for Telegram message. Event: {event}")
                    return
            except Exception as e:
                logger.error(f"No chat_id in user record for Telegram message. Event: {event}, error: {e}", exc_info=True)
                return

        if response_text:
            await self.telegram_client.send_message(chat_id, response_text)
            if response_files:
                for file_obj in response_files:
                    await self.telegram_client.send_media(chat_id, file_obj)
        logger.info(f"Successfully sent response to Telegram user {chat_id}")

    async def _send_slack_response(self, event: dict, response_text: str, response_files):
        """Send response to Slack channel or DM."""
        user_id = event.get("user_id")
        if not user_id:
            logger.error(f"No user_id in event for Slack message. Event: {event}")
            return

        # Get channel from event metadata
        channel = event.get("metadata", {}).get("channel")
        thread_ts = event.get("metadata", {}).get("thread_ts")  # Reply in thread if available

        if not channel:
            logger.error(f"No channel in event metadata for Slack message. Event: {event}")
            return

        try:
            # Initialize Slack client for this user
            from src.integrations.slack.slack_client import SlackIntegration
            slack_integration = SlackIntegration(user_id)

            if not await slack_integration.authenticate():
                logger.error(f"Failed to authenticate Slack for user {user_id}")
                return

            # Send message (will auto-select workspace if user has only one)
            if response_text:
                await slack_integration.send_message(
                    channel=channel,
                    text=response_text,
                    thread_ts=thread_ts  # Reply in thread
                )

            # Note: File attachments not implemented yet for Slack
            if response_files:
                logger.warning("Slack file attachments not yet implemented")

            logger.info(f"Successfully sent response to Slack channel {channel}")

        except Exception as e:
            logger.error(f"Failed to send Slack response: {e}", exc_info=True)

    async def _send_discord_response(self, event: dict, response_text: str, response_files):
        """Send response to Discord using interaction webhook."""
        metadata = event.get("metadata", {})
        interaction_token = metadata.get("interaction_token")
        application_id = metadata.get("application_id")

        # If this is an interaction (slash command), use webhook follow-up
        if interaction_token and application_id:
            logger.info(f"Sending Discord interaction follow-up response")

            try:
                import httpx
                import os

                # Use Discord interaction webhook to edit the initial message
                # This replaces "Processing..." with the actual response
                async with httpx.AsyncClient() as client:
                    response = await client.patch(
                        f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}/messages/@original",
                        headers={"Content-Type": "application/json"},
                        json={"content": response_text}
                    )

                    if response.status_code not in [200, 201]:
                        logger.error(f"Discord follow-up failed: {response.status_code} - {response.text}")
                        return

                    logger.info("Successfully sent Discord interaction follow-up")
                    return

            except Exception as e:
                logger.error(f"Failed to send Discord follow-up: {e}", exc_info=True)
                return

        # Fallback: regular message send (for non-interaction events)
        user_id = event.get("user_id")
        channel = metadata.get("channel")

        if not user_id or not channel:
            logger.error(f"Missing user_id or channel for Discord message")
            return

        try:
            from src.integrations.discord.discord_client import DiscordIntegration
            discord_integration = DiscordIntegration(user_id)

            if not await discord_integration.authenticate():
                logger.error(f"Failed to authenticate Discord for user {user_id}")
                return

            if response_text:
                await discord_integration.send_message(
                    channel=channel,
                    text=response_text
                )

            if response_files:
                logger.warning("Discord file attachments not yet implemented")

            logger.info(f"Successfully sent response to Discord channel {channel}")

        except Exception as e:
            logger.error(f"Failed to send Discord response: {e}", exc_info=True)

    async def _send_webhook_reponse(self, event, response_text):
        logging.info('attempting to publish to websocket')
        token = event.get("metadata", {}).get("token")
        if not token:
            logger.error(f"No user_id in event for WebSocket message. Event: {event}")
            return

        # The channel name must match what the ingress WebSocket endpoint subscribes to.
        channel = f"ws-out:{token}"
        await publish_message(channel, response_text)
        logger.info(f"Successfully published response to Redis channel '{channel}' for token {token}, which belongs to user {event.get('user_id')}")

    async def _send_mcp_response(self, event: dict, response_text: str, response_files):
        """Send response to MCP client via Redis pub/sub."""
        response_channel = event.get("metadata", {}).get("response_channel")
        mcp_request_id = event.get("metadata", {}).get("mcp_request_id")

        if not response_channel:
            logger.error(f"No response_channel in event metadata for MCP response. Event: {event}")
            return

        try:
            # Build response payload matching MCPResponse schema
            response_payload = {
                "response": response_text,
                "delivery_platform": "mcp",
                "execution_notes": None,
                "output_modality": "text",
                "file_links": response_files or []
            }

            # Publish to the response channel that the MCP endpoint is waiting on
            import json
            await publish_message(response_channel, json.dumps(response_payload))

            logger.info(f"Successfully published MCP response to channel '{response_channel}' for request {mcp_request_id}")

        except Exception as e:
            logger.error(f"Failed to send MCP response: {e}", exc_info=True)

    async def send_response(self, event: dict, result: dict):
        """
        Routes the final response to the appropriate channel based on the event source.
        Handles location requests and sending in addition to text/media responses.
        """
        source = event.get("source")
        ### cast to lower-case to avoid case sensitivity issues
        if source and isinstance(source, str):
            source = source.lower()
        response_text = result.get("response", "Sorry, something went wrong.")
        response_files = result.get("file_links", [])
        logger.info(f"the following response payload will be sent: text: {response_text}, files: {response_files}")

        # Handle location functionality (request or send)
        request_location = event.get("request_location", False)
        send_location_data = event.get("send_location")

        if not source and not event.get('output_type'):
            logger.error(f"No source or output type found in event metadata. Cannot route response. Event: {event}")
            return

        logger.info(f"Routing response for source: {source}, output_type: {event.get('output_type')}")
        if event.get('output_type') not in ['email','websocket','telegram','whatsapp','imessage','slack','discord','mcp'] and event.get('source') in ['scheduled','recurring']:
            logger.info('incorrect output type for scheduled or recurring event')
            if event.get('metadata',{}).get('original_source', None):
                logger.info(f"Overriding event source from {event['output_type']} to {event['metadata']['original_source']}")
                event['output_type'] = event['metadata']['original_source']

        try:
            final_output_type = event.get("output_type", source)

            # Handle location request
            if request_location:
                logger.info(f"Location request detected for platform: {final_output_type}")
                if final_output_type == "telegram":
                    chat_id = event.get("output_chat_id")
                    if not chat_id:
                        integration_record = await integration_service.get_integration_record_for_user_and_name(
                            user_id=event.get("user_id"), name="telegram"
                        )
                        if integration_record:
                            chat_id = integration_record.get("telegram_chat_id")
                    if chat_id:
                        await self.telegram_client.request_location(chat_id, response_text)
                        logger.info(f"Location request sent via Telegram to chat {chat_id}")
                        return  # Location request sent, no need to send regular message

                elif final_output_type == "whatsapp":
                    phone_number = event.get("output_phone_number")
                    if not phone_number and event.get("user_id"):
                        user_record = user_service.get_user_by_id(event.get("user_id"))
                        if user_record:
                            phone_number = user_record.get("phone_number")
                    if phone_number:
                        await self.whatsapp_client.request_location(phone_number, response_text)
                        logger.info(f"Location request sent via WhatsApp to {phone_number}")
                        return  # Location request sent

                elif final_output_type == "imessage":
                    phone_number = event.get("output_phone_number")
                    if not phone_number and event.get("user_id"):
                        user_record = user_service.get_user_by_id(event.get("user_id"))
                        if user_record:
                            phone_number = user_record.get("phone_number")
                    if phone_number:
                        await self.imessage_client.request_location(phone_number, response_text)
                        logger.info(f"Location request sent via iMessage to {phone_number}")
                        return  # Location request sent

            # Handle location send
            if send_location_data:
                logger.info(f"Location send detected for platform: {final_output_type}")
                latitude = send_location_data.get("latitude")
                longitude = send_location_data.get("longitude")
                location_name = send_location_data.get("name", "Location")

                if final_output_type == "telegram":
                    chat_id = event.get("output_chat_id")
                    if not chat_id:
                        integration_record = await integration_service.get_integration_record_for_user_and_name(
                            user_id=event.get("user_id"), name="telegram"
                        )
                        if integration_record:
                            chat_id = integration_record.get("telegram_chat_id")
                    if chat_id:
                        # Send text message first if present
                        if response_text:
                            await self.telegram_client.send_message(chat_id, response_text)
                        # Then send location
                        await self.telegram_client.send_location(chat_id, latitude, longitude, location_name)
                        logger.info(f"Location sent via Telegram to chat {chat_id}")
                        return  # Location sent

                elif final_output_type == "whatsapp":
                    phone_number = event.get("output_phone_number")
                    if not phone_number and event.get("user_id"):
                        user_record = user_service.get_user_by_id(event.get("user_id"))
                        if user_record:
                            phone_number = user_record.get("phone_number")
                    if phone_number:
                        # Send text message first if present
                        if response_text:
                            await self.whatsapp_client.send_message(phone_number, response_text)
                        # Then send location
                        await self.whatsapp_client.send_location(phone_number, latitude, longitude, location_name)
                        logger.info(f"Location sent via WhatsApp to {phone_number}")
                        return  # Location sent

                elif final_output_type == "imessage":
                    phone_number = event.get("output_phone_number")
                    if not phone_number and event.get("user_id"):
                        user_record = user_service.get_user_by_id(event.get("user_id"))
                        if user_record:
                            phone_number = user_record.get("phone_number")
                    if phone_number:
                        # Send text message first if present
                        if response_text:
                            await self.imessage_client.send_message(phone_number, response_text)
                        # Then send location
                        await self.imessage_client.send_location(phone_number, latitude, longitude, location_name)
                        logger.info(f"Location sent via iMessage to {phone_number}")
                        return  # Location sent

            # Normal text/media response handling (if no location was involved or in addition to it)
            if final_output_type == "email":
                await self._send_email_response(event, response_text)

            elif final_output_type == "whatsapp":
                await self._send_whatsapp_reponse(event, response_text, response_files)

            elif final_output_type == "imessage":
                await self._send_imessage_response(event, response_text, response_files)

            elif final_output_type == "telegram":
                await self._send_telegram_response(event, response_text, response_files)

            elif final_output_type == "slack":
                await self._send_slack_response(event, response_text, response_files)

            elif final_output_type == "discord":
                await self._send_discord_response(event, response_text, response_files)

            elif final_output_type == "websocket":
                await self._send_webhook_reponse(event, response_text)

            elif final_output_type == "mcp":
                await self._send_mcp_response(event, response_text, response_files)

            else:
                logger.warning(f"Unknown output target '{final_output_type}'. Cannot route response.")

        except Exception as e:
            logger.error(f"Failed to send response for source '{source}'. Error: {e}", exc_info=True)

# Singleton instance for easy access
egress_service = EgressService()
