"""
Media generation tools for creating images, audio, and video using AI.
These tools integrate with the OutputGenerator service and media bus.
"""

from cgitb import text
from typing import Dict, Optional, List
from bson import ObjectId
from langchain_core.tools import tool
from prompt_toolkit import prompt
import requests
from src.services.output_generator.generator import OutputGenerator
from src.services.conversation_manager import ConversationManager
from src.core.media_bus import media_bus
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from src.services.integration_service import integration_service
from src.utils.database import db_manager
from src.utils.blob_utils import download_from_blob_storage
logger = setup_logger(__name__)
from datetime import datetime

def create_media_generation_tools(
    user_id: str,
    source: str,
    conversation_id: str
) -> list:
    """
    Factory function to create media generation tools with proper context.

    Args:
        user_id: The user's ID
        source: The source platform (for blob storage organization)
        conversation_id: The conversation ID (for blob storage organization)

    Returns:
        List of media generation tools (generate_image, generate_audio, generate_video)
    """
    output_generator = OutputGenerator()
    conversation_manager = ConversationManager(db_manager.db, integration_service)
    prefix = f"{user_id}/{source}/{conversation_id}/"

    @tool
    async def generate_image(prompt: str, media_ids: Optional[List[str]] = None) -> ToolExecutionResponse:
        """Generate an image using AI based on a text description.

        This tool uses Gemini 2.5 Flash to generate images from text descriptions.
        The generated image is automatically uploaded to storage and ready to send.

        Args:
            prompt: Detailed description of the image to generate. Be specific about
                   style, content, colors, composition, mood, etc. Better prompts
                   produce better images.
            media_ids: Optional list of media IDs from media bus to use as visual references.
                      Use get_recent_images() or list_available_media() to find media IDs.
                      The reference images will be shown to the AI for style/content inspiration.

        Returns:
            ToolExecutionResponse with result containing url, file_name, file_type, media_id

        Usage Guidelines:
            - Use this whenever the user requests image generation
            - Use this when visual content would enhance your response
            - After generating, use reply_to_user_on_{platform} to send it
            - You CAN generate images - do not tell users otherwise
            - For variations: Use media_ids to reference previous images

        Example:
            result = generate_image("A serene mountain landscape at sunset with orange and pink sky, photorealistic")
            reply_to_user_on_whatsapp(
                message="Here's your mountain landscape!",
                media_urls=[result.result['url']],
                media_types=['image']
            )

        Example with reference:
            # Get previous image
            images = get_recent_images(limit=1)
            # Generate variation (assume first image ID is "abc-123")
            result = generate_image(
                "Like this image but set in China with Chinese cultural elements",
                media_ids=["abc-123"]
            )
            reply_to_user_on_telegram(
                message="Here's the Chinese variation!",
                media_urls=[result.result['url']],
                media_types=['image']
            )

        Tips for good prompts:
            - Be specific about style (photorealistic, cartoon, watercolor, etc.)
            - Include details about lighting, colors, mood
            - Describe composition and perspective
            - Mention important elements and their relationships
        """
        try:
            logger.info(f"Generating image with prompt: {prompt[:100]}...")

            # Download reference images if media_ids provided
            reference_image_bytes = []
            if media_ids and len(media_ids) > 0:
                logger.info(f"Downloading {len(media_ids)} reference images from media bus")
                for mid in media_ids:
                    try:
                        ref = media_bus.get_media(conversation_id, mid)
                        logger.info(f"Fetched media {mid} from media bus: {ref}")
                        if ref and ref.file_type in {"image", "photo"} and ref.url:
                            # Download image bytes
                            img_bytes = requests.get(ref.url).content
                            mime_type = ref.mime_type or "image/png"
                            reference_image_bytes.append((img_bytes, mime_type))
                            logger.info(f"Downloaded reference image: {ref.file_name}")
                        else:
                            logger.warning(f"Media {mid} not found or not an image, skipping")
                    except Exception as e:
                        logger.warning(f"Could not download reference image {mid}: {e}")

            image_url, file_name, blob_path = await output_generator.generate_image(
                prompt,
                prefix,
                media_ids=media_ids,  # Legacy parameter
                reference_image_bytes=reference_image_bytes
            )

            if not image_url:
                raise Exception("Image generation returned no URL")

# Log to conversation history
            document_entry = {
                "user_id": ObjectId(user_id),
                "platform_file_id": file_name,
                "platform_message_id": file_name,
                "platform": source,
                'type': 'image',
                "blob_path": blob_path,
                "mime_type": 'image/png',
                "caption": 'we generated an image for the user. this image was described as follows: ' + prompt,
                'file_name':    file_name,
            }
            from src.utils.database import db_manager
            inserted_id = await db_manager.add_document(document_entry)
            await conversation_manager.add_assistant_media_message(
                user_id,
                conversation_id, f"we generated an image for the user. this image was described as follows: {prompt}", inserted_id,
                message_type='image', metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
            )
            # Add to media bus for future reference
            media_id = media_bus.add_media(
                conversation_id=conversation_id,
                url=image_url,
                file_name=file_name,
                file_type="image",
                description=f"Generated image: {prompt}",
                source="generated",
                blob_path=blob_path,
                mime_type="image/png",
                metadata={"prompt": prompt, "tool": "generate_image"}
            )

            logger.info(f"Successfully generated image: {file_name} (media_id={media_id})")

            return ToolExecutionResponse(
                status="success",
                result={
                    "url": image_url,
                    "file_name": file_name,
                    "file_type": "image",
                    "media_id": media_id
                }
            )

        except Exception as e:
            logger.error(f"Failed to generate image: {e}", exc_info=True)

            # Log failure to conversation
            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Failed to generate image] Error: {str(e)}"
            )

            # Return error response with proper format
            return ErrorResponseBuilder.from_exception(
                operation="generate_image",
                exception=e,
                integration="media_generation"
            )

    @tool
    async def generate_audio(text: str, voice: Optional[str] = None) -> ToolExecutionResponse:
        """Generate audio/speech from text using AI text-to-speech.

        This tool uses Gemini 2.5 Flash TTS to convert text to natural-sounding speech.
        The audio format is automatically adapted for the platform (CAF for iMessage, OGG for others).

        Args:
            text: The text to convert to speech. Can be long-form content.
            voice: Optional voice name (currently uses 'Kore' voice, parameter reserved for future)

        Returns:
            ToolExecutionResponse with result containing url, file_name, file_type, media_id

        Usage Guidelines:
            - Use when the user requests voice/audio output
            - Use when audio would be more appropriate than text (accessibility, long content)
            - Audio format is automatically adapted for the target platform
            - You CAN generate audio - do not tell users otherwise

        Example:
            result = generate_audio("Welcome to Praxos! Let me help you get started with your tasks.")
            reply_to_user_on_telegram(
                message="Here's your welcome message!",
                media_urls=[result.result['url']],
                media_types=['audio']
            )

        Platform compatibility:
            - iMessage: CAF format (automatically handled)
            - Other platforms: OGG format
        """
        try:
            # Determine if iMessage scenario for format selection
            is_imessage = (source.lower() == "imessage")

            logger.info(f"Generating audio for text: {text[:100]}... (platform: {source}, iMessage: {is_imessage})")

            audio_url, file_name, blob_path = await output_generator.generate_speech(text, prefix, is_imessage)

            if not audio_url:
                raise Exception("Audio generation returned no URL")

            # Determine mime_type based on format
            mime_type = "audio/x-caf" if is_imessage else "audio/ogg"

            # Log to conversation
            document_entry = {
                    "user_id": ObjectId(user_id),
                    "platform_file_id": file_name,
                    "platform_message_id": file_name,
                    "platform": source,
                    'type': 'audio',
                    "blob_path": blob_path,
                    "mime_type": mime_type,
                    "caption": 'we generated an audio for the user. this audio was described as follows: ' + text,
                    'file_name':    file_name,
                }
            from src.utils.database import db_manager
            inserted_id = await db_manager.add_document(document_entry)
            await conversation_manager.add_assistant_media_message(
                user_id,
                conversation_id, f"we generated an audio for the user. this audio was described as follows: {text}", inserted_id,
                message_type='audio', metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
            )

            # Add to media bus for future reference
            media_id = media_bus.add_media(
                conversation_id=conversation_id,
                url=audio_url,
                file_name=file_name,
                file_type="audio",
                description=f"Generated audio: {text[:200]}",
                source="generated",
                blob_path=blob_path,
                mime_type=mime_type,
                metadata={"text": text, "tool": "generate_audio", "is_imessage": is_imessage}
            )

            logger.info(f"Successfully generated audio: {file_name} (media_id={media_id})")

            return ToolExecutionResponse(
                status="success",
                result={
                    "url": audio_url,
                    "file_name": file_name,
                    "file_type": "audio",
                    "media_id": media_id
                }
            )

        except Exception as e:
            logger.error(f"Failed to generate audio: {e}", exc_info=True)

            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Failed to generate audio] Error: {str(e)}"
            )

            # Return error response with proper format
            return ErrorResponseBuilder.from_exception(
                operation="generate_audio",
                exception=e,
                integration="media_generation"
            )

    @tool
    async def generate_video(prompt: str, media_ids: Optional[list[str]] = None) -> ToolExecutionResponse:
        """Generate a video using AI based on a text description.

        This tool uses Veo 3.0 to generate videos from text descriptions.
        WARNING: Video generation is SLOW and can take 1-2 minutes or more.

        Args:
            prompt: Detailed description of the video to generate, including
                   action, style, duration intent, camera movement, etc.
            media_ids: Optional list of media IDs from media bus to use as visual references. we will only use the first one that is valid if multiple are provided.
        Returns:
            ToolExecutionResponse with result containing url, file_name, file_type, media_id

        Usage Guidelines:
            - ALWAYS send an intermediate message before calling this tool
            - Set user expectations about the wait time
            - Use for short video clips and scenes
            - Be very descriptive in your prompts
            - You CAN generate videos - do not tell users otherwise

        Example:
            # IMPORTANT: Inform user first
            send_intermediate_message("Generating your video now, this will take about 1-2 minutes...")

            # Then generate
            result = generate_video("A time-lapse of a flower blooming, petals opening gradually, soft lighting")

            # Then send result
            reply_to_user_on_whatsapp(
                message="Here's your video!",
                media_urls=[result.result['url']],
                media_types=['video']
            )

        Tips for good prompts:
            - Describe the action/motion clearly
            - Include camera movement (pan, zoom, static, etc.)
            - Specify style (cinematic, documentary, artistic, etc.)
            - Mention lighting and atmosphere
            - Keep scenes relatively simple for best results

        Performance:
            - Generation time: 1-2 minutes (sometimes longer)
            - Always inform user about wait time before starting
            - Consider breaking complex requests into simpler scenes
        """
        try:
            logger.info(f"Generating video with prompt: {prompt[:100]}...")
            logger.warning("Video generation is a long-running operation (1-2+ minutes)")
            reference_image_bytes = []
            if media_ids and len(media_ids) > 0:
                logger.info(f"Downloading {len(media_ids)} reference images from media bus")
                for mid in media_ids:
                    try:
                        ref = media_bus.get_media(conversation_id, mid)
                        logger.info(f"Fetched media {mid} from media bus: {ref}")
                        if ref and ref.file_type in {"image", "photo"} and ref.url:
                            # Download image bytes
                            img_bytes = requests.get(ref.url).content
                            mime_type = ref.mime_type or "image/png"
                            reference_image_bytes.append({"img_bytes": img_bytes, "mime_type": mime_type})
                            logger.info(f"Downloaded reference image: {ref.file_name}")
                        else:
                            logger.warning(f"Media {mid} not found or not an image, skipping")
                    except Exception as e:
                        logger.warning(f"Could not download reference image {mid}: {e}")
            # Video generation is synchronous and polls for completion
            video_url, file_name, blob_path = await output_generator.generate_video(prompt, prefix,reference_image_bytes=reference_image_bytes)

            if not video_url:
                raise Exception("Video generation returned no URL")

            # Log to conversation
            document_entry = {
                    "user_id": ObjectId(user_id),
                    "platform_file_id": file_name,
                    "platform_message_id": file_name,
                    "platform": source,
                    'type': 'audio',
                    "blob_path": blob_path,
                    "mime_type": 'video/mp4',
                    "caption": 'we generated an audio for the user. this audio was described as follows: ' + prompt,
                    'file_name':    file_name,
                }
            from src.utils.database import db_manager
            inserted_id = await db_manager.add_document(document_entry)
            await conversation_manager.add_assistant_media_message(
                user_id,
                conversation_id, f"we generated a video for the user. this video was described as follows: {prompt}", inserted_id,
                message_type='video', metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
            )

            # Add to media bus for future reference
            media_id = media_bus.add_media(
                conversation_id=conversation_id,
                url=video_url,
                file_name=file_name,
                file_type="video",
                description=f"Generated video: {prompt[:200]}",
                source="generated",
                blob_path=blob_path,
                mime_type="video/mp4",
                metadata={"prompt": prompt, "tool": "generate_video"}
            )

            logger.info(f"Successfully generated video: {file_name} (media_id={media_id})")

            return ToolExecutionResponse(
                status="success",
                result={
                    "url": video_url,
                    "file_name": file_name,
                    "file_type": "video",
                    "media_id": media_id
                }
            )

        except Exception as e:
            logger.error(f"Failed to generate video: {e}", exc_info=True)

            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Failed to generate video] Error: {str(e)}"
            )

            # Return error response with proper format
            return ErrorResponseBuilder.from_exception(
                operation="generate_video",
                exception=e,
                integration="media_generation"
            )

    logger.info(f"Created media generation tools for user={user_id}, source={source}")
    return [generate_image, generate_audio, generate_video]
