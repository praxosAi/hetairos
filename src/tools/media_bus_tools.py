"""
Media Bus Tools: Agent tools for accessing the media reference system.

These tools provide the agent with access to media that has been generated
or received during the current conversation, enabling:
- Listing available media
- Retrieving specific media by ID
- Quick access to recent images for reference/inspiration
"""

from typing import Optional, Dict
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from src.core.media_bus import media_bus
from src.services.conversation_manager import ConversationManager
from src.services.integration_service import integration_service
from src.utils.database import db_manager

from src.utils.logging import setup_logger

logger = setup_logger(__name__)


def create_media_bus_tools(conversation_id: str, user_id: str) -> list:
    """
    Factory to create media bus tools for a specific conversation.

    Args:
        conversation_id: The conversation ID to scope the tools to
        user_id: The user's ID for conversation history updates

    Returns:
        List of media bus access tools
    """
    conversation_manager = ConversationManager(db_manager.db, integration_service)

    @tool
    async def list_available_media(media_type: Optional[str] = None, limit: int = 10) -> str:
        """List media items currently available in this conversation.

        This tool shows all media that has been generated or received during
        the current conversation. Use this to see what media exists that you
        can reference or build upon.

        Args:
            media_type: Optional filter by type - 'image', 'audio', 'video', or 'document'
            limit: Maximum number of items to return (default 10, max 50)

        Returns:
            Formatted string describing available media with IDs, descriptions, and URLs

        Usage:
            - Check what images were generated: list_available_media(media_type='image')
            - See all recent media: list_available_media()
            - Get specific media details, then use get_media_by_id() for full info

        Example:
            media_list = list_available_media(media_type='image', limit=5)
            # Returns formatted list with media IDs and descriptions
            # Use these IDs with get_media_by_id() to get URLs for sending
        """
        try:
            # Validate limit
            limit = max(1, min(limit, 50))

            refs = media_bus.list_media(
                conversation_id,
                file_type=media_type,
                limit=limit
            )

            if not refs:
                type_msg = f" of type '{media_type}'" if media_type else ""
                return f"No media items{type_msg} currently available in this conversation."

            # Format results
            result = f"Available media items ({len(refs)}):\n\n"

            for i, ref in enumerate(refs, 1):
                result += f"{i}. [{ref.file_type.upper()}] ID: {ref.media_id}\n"
                result += f"   Description: {ref.description}\n"
                result += f"   File: {ref.file_name}\n"
                result += f"   Source: {ref.source}\n"
                result += f"   Created: {ref.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                if i < len(refs):  # Not last item
                    result += "\n"

            logger.info(f"Listed {len(refs)} media items for conversation {conversation_id}")
            return result

        except Exception as e:
            logger.error(f"Error listing media: {e}", exc_info=True)
            return f"Error listing media: {str(e)}"

    @tool
    async def get_media_by_id(media_id: str) -> Dict[str, str]:
        """Retrieve a specific media item by its ID and load it into conversation context.

        This tool retrieves media from the media bus and adds it to the current conversation
        context, allowing you to "see" and reason about it. This is essential when you need to:
        - Reference or analyze previously generated media
        - Create variations based on existing media
        - Understand what was generated earlier in the conversation

        After calling this tool, the media will be visible to you in the conversation context.

        Args:
            media_id: The unique ID of the media item (from list_available_media)

        Returns:
            Dictionary with 'url', 'file_name', 'file_type', 'description', and 'source'

        Important:
            - This loads the media into your context so you can "see" it
            - For images, you'll be able to visually analyze the content
            - For audio/video, you'll see a description
            - Use the returned URL to send the media to the user

        Usage:
            1. List media: list_available_media()
            2. Load media: media = get_media_by_id("abc-123-def")
            3. Now you can see the media and reason about it
            4. Send to user: reply_to_user_on_whatsapp(
                   message="Here's that image again!",
                   media_urls=[media['url']],
                   media_types=[media['file_type']]
               )

        Example:
            # Reference and analyze previously generated image
            media = get_media_by_id("550e8400-e29b-41d4-a716-446655440000")
            # Now you can see the image and create a variation
            new_img = generate_image("Like the image I just loaded, but with darker colors")
        """
        try:
            ref = media_bus.get_media(conversation_id, media_id)

            if not ref:
                raise Exception(f"Media not found with ID: {media_id}")

            logger.info(f"Retrieved media {media_id} from bus: {ref.file_name}")

            # Build LLM-compatible payload based on media type
            payload = None
            if ref.file_type in {"image", "photo"}:
                # Images can be directly viewed by the LLM via URL
                payload = {"type": "image_url", "image_url": ref.url}
            else:
                # For audio/video/documents, provide textual description
                # (LLM can't directly process these, but can reason about descriptions)
                payload = {
                    "type": "text",
                    "text": f"[{ref.file_type.upper()}] {ref.description}\nFile: {ref.file_name}\nURL: {ref.url}"
                }

            # Add to conversation history so agent can reference it
            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Retrieved media from bus] {ref.description}",
                metadata={"media_id": media_id, "media_type": ref.file_type, "action": "media_retrieval"}
            )

            logger.info(f"Added media {media_id} to conversation context (type={ref.file_type})")

            # Return media details for sending
            return {
                "url": ref.url,
                "file_name": ref.file_name,
                "file_type": ref.file_type,
                "description": ref.description,
                "source": ref.source,
                "media_id": ref.media_id,
                "message": f"Media loaded into context. {ref.description}"
            }

        except Exception as e:
            logger.error(f"Error getting media by ID {media_id}: {e}", exc_info=True)
            raise Exception(f"Failed to retrieve media: {str(e)}")

    @tool
    async def get_recent_images(limit: int = 5) -> str:
        """Get recently generated or uploaded images.

        Quick access to recent images without needing to filter the full list.
        Useful for referencing previous images or creating variations.

        Args:
            limit: Maximum number of images to return (default 5, max 20)

        Returns:
            Formatted string with image IDs, descriptions, and URLs

        Usage:
            - See what images exist: get_recent_images()
            - Use descriptions to understand what was generated
            - Use IDs with get_media_by_id() to get URLs for sending or reference
            - Use descriptions in new prompts: "Create a variation of [description] but with darker colors"

        Example:
            images = get_recent_images(limit=3)
            # Review what was generated
            # Then create variation:
            new_image = generate_image("Like the sunset landscape but at dawn instead")
        """
        try:
            # Validate limit
            limit = max(1, min(limit, 20))

            refs = media_bus.list_media(
                conversation_id,
                file_type="image",
                limit=limit
            )

            if not refs:
                return "No images currently available in this conversation."

            # Format results
            result = f"Recent images ({len(refs)}):\n\n"

            for i, ref in enumerate(refs, 1):
                result += f"{i}. ID: {ref.media_id}\n"
                result += f"   Description: {ref.description}\n"
                result += f"   File: {ref.file_name}\n"
                result += f"   URL: {ref.url}\n"
                if i < len(refs):  # Not last item
                    result += "\n"

            logger.info(f"Retrieved {len(refs)} recent images for conversation {conversation_id}")
            return result

        except Exception as e:
            logger.error(f"Error getting recent images: {e}", exc_info=True)
            return f"Error getting recent images: {str(e)}"

    logger.info(f"Created media bus tools for conversation {conversation_id}")
    return [list_available_media, get_media_by_id, get_recent_images]
