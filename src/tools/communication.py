from typing import List, Dict, Optional
from langchain_core.tools import tool
from src.egress.service import egress_service
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_platform_messaging_tools(
    source: str,
    user_id: str,
    metadata: Optional[Dict] = None,
    available_platforms: Optional[List[str]] = None
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
    source_tool = _create_reply_tool(source, user_id, metadata)
    tools.append(source_tool)

    # Optionally create tools for other connected platforms
    if available_platforms:
        for platform in available_platforms:
            if platform.lower() != source.lower() and platform.lower() not in ['email']:
                platform_tool = _create_reply_tool(platform.lower(), user_id, metadata)
                tools.append(platform_tool)

    logger.info(f"Created {len(tools)} platform messaging tools for source={source}")
    return tools


def _create_reply_tool(platform: str, user_id: str, metadata: Optional[Dict] = None):
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
    Returns:
        Success confirmation or raises exception on failure

    Important:
        - For media, first generate it using generate_image/generate_audio/generate_video tools
        - Then pass the returned URLs to this tool via media_urls and media_types parameters
        - You can send text-only messages or messages with media attachments
        - This is NOT optional - you MUST use this tool to communicate responses to the user

    Examples:
        reply_to_user_on_{platform_lower}(message="Hello! How can I help you?")

        # With media:
        result = generate_image("sunset over mountains")
        reply_to_user_on_{platform_lower}(
            message="Here's your image!",
            media_urls=[result['url']],
            media_types=['image']
        )
    """

    @tool(name_or_callable=f"reply_to_user_on_{platform_lower}", description=tool_description)
    async def reply_to_user_on_platform(
        message: str,
        media_urls: Optional[List[str]] = None,
        media_types: Optional[List[str]] = None,
        final_message: bool = True
    ) -> ToolExecutionResponse:
        try:
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

            # Build event structure for egress
            event = {
                "source": metadata.get("source") if metadata else platform_lower,
                "output_type": platform_lower,
                "user_id": str(user_id),
                "metadata": metadata or {}
            }

            # Send via egress service
            await egress_service.send_response(
                event=event,
                result={"response": message, "file_links": file_links}
            )

            media_msg = f" with {len(file_links)} media attachment(s)" if file_links else ""
            logger.info(f"Successfully sent {platform} message to user{media_msg}")
            if final_message:
                logger.info(f"This was marked as the final message to be sent to the user on {platform}")
                return ToolExecutionResponse(
                    status="success",
                    result=f"Final message sent successfully to user on {platform}{media_msg}",
                    final_message=True,
                )
            return ToolExecutionResponse(
                status="success",
                result=f"Message sent successfully to user on {platform}{media_msg}"
            )

        except Exception as e:
            logger.error(f"Failed to send {platform} message: {e}", exc_info=True)
            # Per user spec: throw exception (robust error handling system will catch it)
            raise Exception(f"Failed to send message to user on {platform}: {str(e)}")

    # Tool name and description already set via @tool decorator
    return reply_to_user_on_platform


def create_bot_communication_tools(metadata: Optional[Dict] = None, user_id: str = None) -> List:
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

    return [send_intermediate_message, reply_to_user_via_email, send_new_email_as_praxos_bot, report_bug_to_developers]
