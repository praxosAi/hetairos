from typing import List, Dict, Optional
from langchain_core.tools import tool
from src.egress.service import egress_service
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from src.services.conversation_manager import ConversationManager
from src.integrations.ios.client import IOSClient
logger = setup_logger(__name__)

def create_platform_messaging_tools(
    source: str,
    user_id: str,
    metadata: Optional[Dict] = None,
    available_platforms: Optional[List[str]] = None,
    conversation_manager: ConversationManager = None,
    tool_registry = None,
) -> List:
    """
    Create platform-specific messaging tools for communicating with the user.

    Args:
        source: The source platform (whatsapp, telegram, imessage, etc.)
        user_id: The user's ID
        metadata: Event metadata for routing
        available_platforms: List of platforms the user has connected (optional)

    Returns:
        List of messaging tools including source platform and optionally others
    """
    tools = []
    # Always create tool for source platform
    source_tool = _create_reply_tool(source, user_id, metadata, conversation_manager)
    tools.append(source_tool)

    # Optionally create tools for other connected platforms
    if available_platforms:
        for platform in available_platforms:
            if platform.lower() != source.lower() and platform.lower() not in ['email']:
                platform_tool = _create_reply_tool(platform.lower(), user_id, metadata)
                tools.append(platform_tool)

    logger.info(f"Created {len(tools)} platform messaging tools for source={source}")
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(tools)
    return tools


def _create_reply_tool(platform: str, user_id: str, metadata: Optional[Dict] = None, conv_manager: ConversationManager = None):
    """Factory to create a platform-specific reply tool."""

    platform_lower = platform.lower()

    # Build description outside function to avoid f-string docstring issues
    tool_description = f"""Send a {platform} message to the user.

    This tool sends messages directly to the user's {platform} account. Use this to communicate
    ALL responses to the user. You can send multiple messages during a conversation.

    Args:
        message: The text message to send to the user
        media_urls: Optional list of media URLs to attach (from generate_image/generate_audio/generate_video)
        media_types: Optional list of media types corresponding to URLs (image, audio, video, document)
        final_message: Whether this is the final message in the conversation (default True). if you think you will send more messages later, set to False.
        request_location: Whether to request the user's location (default False). When True, sends a location request appropriate for the platform.
        send_location_latitude: Latitude coordinate to send a location to the user (requires send_location_longitude)
        send_location_longitude: Longitude coordinate to send a location to the user (requires send_location_latitude)
        send_location_name: Optional name/label for the location being sent (e.g., "Office", "Meeting Point")

    Returns:
        Success confirmation or raises exception on failure

    Important:
        - For media, first generate it using generate_image/generate_audio/generate_video tools
        - Then pass the returned URLs to this tool via media_urls and media_types parameters
        - You can send text-only messages or messages with media attachments
        - This is NOT optional - you MUST use this tool to communicate responses to the user
        - For locations: Use request_location to ask user for their location, or send_location_* parameters to send a location
        - Location requests work on all platforms (Telegram/WhatsApp have native buttons, iMessage uses text prompt)
        - Location sending works on all platforms (Telegram/WhatsApp native, iMessage as Apple Maps URL)

    Examples:
        reply_to_user_on_{platform_lower}(message="Hello! How can I help you?")

        # With media:
        result = generate_image("sunset over mountains")
        reply_to_user_on_{platform_lower}(
            message="Here's your image!",
            media_urls=[result['url']],
            media_types=['image']
        )

        # Requesting location:
        reply_to_user_on_{platform_lower}(
            message="I'll need your location to help with that.",
            request_location=True
        )

        # Sending location:
        reply_to_user_on_{platform_lower}(
            message="Meet me at this location!",
            send_location_latitude=40.7128,
            send_location_longitude=-74.0060,
            send_location_name="Office"
        )
    """

    @tool(name_or_callable=f"reply_to_user_on_{platform_lower}", description=tool_description)
    async def reply_to_user_on_platform(
        message: str,
        media_urls: Optional[List[str]] = None,
        media_types: Optional[List[str]] = None,
        final_message: bool = True,
        request_location: bool = False,
        send_location_latitude: Optional[float] = None,
        send_location_longitude: Optional[float] = None,
        send_location_name: Optional[str] = None
    ) -> ToolExecutionResponse:
        try:
            logger.info(f"Sending {platform_lower} message to user: {message}, with {len(media_urls) if media_urls else 0} media attachments")
            # Build file_links from media
            file_links = []
            if media_urls and media_types:
                if len(media_urls) != len(media_types):
                    raise ValueError(f"media_urls and media_types must have same length (got {len(media_urls)} and {len(media_types)})")

                for url, media_type in zip(media_urls, media_types):
                    file_name = url.split('/')[-1] if '/' in url else "media_file"
                    file_links.append({
                        "url": url,
                        "file_type": media_type,
                        "file_name": file_name
                    })
                logger.info(f"Prepared {len(file_links)} media attachments for {platform}")

            # Validate and prepare location data
            location_data = None
            if send_location_latitude is not None and send_location_longitude is not None:
                # Validate coordinates
                if not (-90 <= send_location_latitude <= 90):
                    raise ValueError(f"Invalid latitude: {send_location_latitude}. Must be between -90 and 90.")
                if not (-180 <= send_location_longitude <= 180):
                    raise ValueError(f"Invalid longitude: {send_location_longitude}. Must be between -180 and 180.")

                location_data = {
                    "latitude": send_location_latitude,
                    "longitude": send_location_longitude,
                    "name": send_location_name or "Location"
                }
                logger.info(f"Prepared location data: {location_data}")
            elif send_location_latitude is not None or send_location_longitude is not None:
                raise ValueError("Both send_location_latitude and send_location_longitude must be provided together.")

            # Build event structure for egress
            event = {
                "source": metadata.get("source") if metadata else platform_lower,
                "output_type": platform_lower,
                "user_id": str(user_id),
                "metadata": metadata or {}
            }

            # Add location flags to event
            if request_location:
                event["request_location"] = True
                logger.info(f"Location request enabled for {platform}")
            if location_data:
                event["send_location"] = location_data
                logger.info(f"Location send enabled for {platform}: {location_data}")
            ###
            # Send via egress service
            await egress_service.send_response(
                event=event,
                result={"response": message, "file_links": file_links}
            )
            try:
                await conv_manager.add_assistant_message(user_id, metadata['conversation_id'], message)
            except Exception as e:
                logger.error(f"Failed to log assistant message to conversation manager: {e}", exc_info=True)

            # Build success message with all components
            media_msg = f" with {len(file_links)} media attachment(s)" if file_links else ""
            location_msg = ""
            if request_location:
                location_msg += " (location requested)"
            if location_data:
                location_msg += f" (location sent: {location_data['name']})"

            logger.info(f"Successfully sent {platform} message to user{media_msg}{location_msg}")
            if final_message:
                logger.info(f"This was marked as the final message to be sent to the user on {platform}")
                return ToolExecutionResponse(
                    status="success",
                    result=f"Final message sent successfully to user on {platform}{media_msg}{location_msg}",
                    final_message=True,
                )
            return ToolExecutionResponse(
                status="success",
                result=f"Message sent successfully to user on {platform}{media_msg}{location_msg}"
            )

        except Exception as e:
            logger.error(f"Failed to send {platform} message: {e}", exc_info=True)
            # Per user spec: throw exception (robust error handling system will catch it)
            raise Exception(f"Failed to send message to user on {platform}: {str(e)}")

    # Tool name and description already set via @tool decorator
    return reply_to_user_on_platform


def create_bot_communication_tools(metadata: Optional[Dict] = None, user_id: str = None, tool_registry = None) -> List:
    """Creates tools for the bot to communicate with users on different platforms."""

    @tool
    async def send_intermediate_message(message: str) -> ToolExecutionResponse:
        """
        Sends an intermediate message to the user during long-running operations.
        Use this to notify users that you're working on something that will take time (browsing web, generating media, etc.)
        DO NOT USE THIS IF SIMPLY SENDING AN OUTPUT AT THE END OF YOUR EXECUTION WILL SUFFICE.  USE THIS IF THE GOAL IS TO BROWSE WEB OR GENERATE MEDIA.
        BUT IF THE GOAL IS TO SEND THE MESSAGE TO INFORM THE USER, WHILE WE CONTINUE WORKING ON THEIR REQUEST, THEN YOU MUST USE THIS INSTEAD OF THE FINAL RESPONSE.
        Args:
            message: The status update message to send

        Examples:
            - "I'm browsing that website now, this will take about 30 seconds..."
            - "Generating your image, this may take a minute..."
            - "Searching the web for that information..."
        """
        try:
            source = metadata.get("source") if metadata else "websocket"
            output_type = source if source != "scheduled" else "websocket"

            await egress_service.send_response(
                {
                    "source": source,
                    "output_type": output_type,
                    "metadata": metadata,
                    "user_id": str(user_id)
                },
                {"response": message}
            )
            return ToolExecutionResponse(status="success", result="Intermediate message sent successfully.")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="send_intermediate_message",
                exception=e,
                integration="messaging_service"
            )

    @tool
    async def reply_to_user_via_email(body: str) -> ToolExecutionResponse:
        """
        Sends an email using the Praxos bot. this is specifically for replying to a user's email.
        """
        try:
            await egress_service.send_response({"source": "email", "output_type": "email", "email_type": "reply","original_message": metadata.get("original_message")}, {"response": body})
            return ToolExecutionResponse(status="success", result="Email sent successfully.")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="reply_to_user_via_email",
                exception=e,
                integration="email_service"
            )

    @tool
    async def send_new_email_as_praxos_bot(recipients: List[str], subject: str, body: str) -> ToolExecutionResponse:
        """
        Sends an email using the Praxos bot. this is specifically for sending a new email to someone, as yourself, the mypraxos assistant.
        """
        try:
            await egress_service.send_response({"source": "email", "output_type": "email", "email_type": "new","original_message": metadata.get("original_message"),"new_email_message": {"recipients": recipients, "subject": subject, "body": body}}, {"response": body})
            return ToolExecutionResponse(status="success", result="Email sent successfully.")
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="send_new_email_as_praxos_bot",
                exception=e,
                integration="email_service",
                context={"recipients": recipients}
            )

    @tool
    async def report_bug_to_developers(bug_description: str, additional_context: Optional[str] = None) -> ToolExecutionResponse:
        """
        Reports a bug to the Praxos development team via email.
        Use this when you encounter errors, unexpected behavior, or issues that need developer attention.

        Args:
            bug_description: Detailed description of the bug, including what happened and what was expected
            additional_context: Optional additional context like error messages, stack traces, or reproduction steps
        """
        try:
            dev_emails = ["Soheil@praxos.ai", "Masoud@praxos.ai", "lucas@praxos.ai"]
            subject = "Bug Report from Praxos Agent"

            body = f"""A bug has been reported by the Praxos AI agent:

                    Bug Description:
                    {bug_description}
                    """
            if additional_context:
                body += f"""
                Additional Context:
                {additional_context}
                """

            body += f"""
                    ---
                    Reported by: Agent on behalf of user {user_id}
                    Timestamp: Generated automatically
                    """

            await egress_service.send_response(
                {
                    "source": "email",
                    "output_type": "email",
                    "email_type": "new",
                    "original_message": metadata.get("original_message") if metadata else None,
                    "new_email_message": {
                        "recipients": dev_emails,
                        "subject": subject,
                        "body": body
                    }
                },
                {"response": body}
            )
            return ToolExecutionResponse(
                status="success",
                result=f"Bug report sent successfully to {', '.join(dev_emails)}."
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="report_bug_to_developers",
                exception=e,
                integration="email_service"
            )
    
    # @tool
    # async def send_whatsapp_message_as_praxos_bot(message: str) -> ToolExecutionResponse:
    #     """
    #     Sends a whatsapp message using the Praxos bot. this is specifically for sending the user a whatsapp message. we will handle the phone number for the user.
    #     """
    #     try:
    #         await egress_service.send_response({"source": "whatsapp", "output_type": "whatsapp",'user_id': str(user_id)}, {"response": message})
    #         return ToolExecutionResponse(status="success", result="Whatsapp message sent successfully.")
    #     except Exception as e:
    #         return ToolExecutionResponse(status="error", system_error=str(e))
            
    # @tool
    # async def send_telegram_message_as_praxos_bot(message: str) -> ToolExecutionResponse:
    #     """
    #     Sends a telegram message using the Praxos bot. this is specifically for sending the user a telegram message. we will handle the chat id for the user.
    #     """
    #     try:
    #         await egress_service.send_response({"source": "telegram", "output_type": "telegram",'user_id': str(user_id)}, {"response": message})
    #         return ToolExecutionResponse(status="success", result="Telegram message sent successfully.")
    #     except Exception as e:
    #         return ToolExecutionResponse(status="error", system_error=str(e))

    all_tools = [send_intermediate_message, reply_to_user_via_email, send_new_email_as_praxos_bot, report_bug_to_developers]
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools


def create_ios_command_tools(user_id: str, tool_registry = None) -> List:
    """
    Creates tools for sending commands to iOS Shortcuts.

    These tools allow the agent to trigger actions on the user's iOS device
    via commands sent through iMessage.

    Args:
        user_id: The user's ID

    Returns:
        List of iOS command tools
    """
    ios_client = IOSClient()

    @tool
    async def send_text_via_ios(message: str, target_phone: str) -> ToolExecutionResponse:
        """
        Send a text message via iOS Shortcuts.

        This tool sends a command to the user's iOS device to send a text message
        to another phone number. The iOS Shortcuts automation will execute the command.

        Args:
            message: The text message to send
            target_phone: Phone number to send the message to (format: +1234567890)

        Returns:
            Success confirmation or error message

        Example:
            send_text_via_ios(
                message="Meeting moved to 3pm",
                target_phone="+19292717338"
            )
        """
        try:
            logger.info(f"Sending iOS text command to user {user_id}: msg to {target_phone}")
            result = await ios_client.send_text_message(user_id, message, target_phone)

            if result:
                return ToolExecutionResponse(
                    status="success",
                    result=f"Command sent to iOS device to text {target_phone}: {message}"
                )
            else:
                raise Exception("Failed to send iOS command")

        except Exception as e:
            logger.error(f"Failed to send iOS text command: {e}", exc_info=True)
            raise Exception(f"Failed to send iOS command: {str(e)}")

    @tool
    async def execute_ios_shortcut(shortcut_name: str, input_text: Optional[str] = None) -> ToolExecutionResponse:
        """
        Execute a named iOS Shortcut on the user's device.

        This triggers a specific Shortcut by name, optionally passing input text.
        The user must have a Shortcut with the specified name on their device.

        Args:
            shortcut_name: Name of the Shortcut to execute
            input_text: Optional input text to pass to the Shortcut

        Returns:
            Success confirmation or error message

        Example:
            execute_ios_shortcut(
                shortcut_name="Log Water Intake",
                input_text="500ml"
            )
        """
        try:
            logger.info(f"Sending iOS shortcut command to user {user_id}: {shortcut_name}")
            result = await ios_client.execute_shortcut(user_id, shortcut_name, input_text)

            if result:
                input_msg = f" with input: {input_text}" if input_text else ""
                return ToolExecutionResponse(
                    status="success",
                    result=f"Command sent to iOS device to execute shortcut '{shortcut_name}'{input_msg}"
                )
            else:
                raise Exception("Failed to send iOS command")

        except Exception as e:
            logger.error(f"Failed to send iOS shortcut command: {e}", exc_info=True)
            raise Exception(f"Failed to execute iOS shortcut: {str(e)}")

    @tool
    async def create_ios_reminder(
        title: str,
        due_date: Optional[str] = None,
        notes: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Create a reminder on the user's iOS device.

        This sends a command to create a reminder in the iOS Reminders app.

        Args:
            title: The reminder title/text
            due_date: Optional due date in ISO format (e.g., "2025-11-05T14:00:00")
            notes: Optional additional notes for the reminder

        Returns:
            Success confirmation or error message

        Example:
            create_ios_reminder(
                title="Call dentist",
                due_date="2025-11-05T14:00:00",
                notes="Schedule cleaning appointment"
            )
        """
        try:
            logger.info(f"Sending iOS reminder command to user {user_id}: {title}")
            result = await ios_client.set_reminder(user_id, title, due_date, notes)

            if result:
                return ToolExecutionResponse(
                    status="success",
                    result=f"Command sent to iOS device to create reminder: {title}"
                )
            else:
                raise Exception("Failed to send iOS command")

        except Exception as e:
            logger.error(f"Failed to send iOS reminder command: {e}", exc_info=True)
            raise Exception(f"Failed to create iOS reminder: {str(e)}")

    all_tools = [send_text_via_ios, execute_ios_shortcut, create_ios_reminder]
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools
