"""
Media generation tools for creating images, audio, and video using AI.
These tools integrate with the OutputGenerator service and media bus.
"""

from typing import Dict, Optional
from langchain_core.tools import tool
from src.services.output_generator.generator import OutputGenerator
from src.services.conversation_manager import ConversationManager
from src.core.media_bus import media_bus
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from src.services.integration_service import integration_service
from src.utils.database import db_manager
logger = setup_logger(__name__)

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
    async def generate_image(prompt: str, media_ids: list = []) -> Dict[str, str]:
        """Generate an image using AI based on a text description.

        This tool uses Gemini 2.5 Flash to generate images from text descriptions.
        The generated image is automatically uploaded to storage and ready to send.

        Args:
            prompt: Detailed description of the image to generate. Be specific about
                   style, content, colors, composition, mood, etc. Better prompts
                   produce better images.
            media_ids: Optional list of media IDs to reference for style or content.
                     
        Returns:
            Dictionary with 'url', 'file_name', and 'file_type' keys

        Usage Guidelines:
            - Use this whenever the user requests image generation
            - Use this when visual content would enhance your response
            - After generating, use reply_to_user_on_{platform} to send it
            - You CAN generate images - do not tell users otherwise

        Example:
            result = generate_image("A serene mountain landscape at sunset with orange and pink sky, photorealistic")
            reply_to_user_on_whatsapp(
                message="Here's your mountain landscape!",
                media_urls=[result['url']],
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
            

            image_url, file_name = await output_generator.generate_image(prompt, prefix,media_ids=media_ids)

            if not image_url:
                raise Exception("Image generation returned no URL")

            # Log to conversation history
            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Generated image] {prompt[:200]}"
            )

            # Add to media bus for future reference
            media_id = media_bus.add_media(
                conversation_id=conversation_id,
                url=image_url,
                file_name=file_name,
                file_type="image",
                description=f"Generated image: {prompt[:200]}",
                source="generated",
                metadata={"prompt": prompt, "tool": "generate_image"}
            )

            logger.info(f"Successfully generated image: {file_name} (media_id={media_id})")

            return {
                "url": image_url,
                "file_name": file_name,
                "file_type": "image",
                "media_id": media_id
            }

        except Exception as e:
            logger.error(f"Failed to generate image: {e}", exc_info=True)

            # Log failure to conversation
            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Failed to generate image] Error: {str(e)}"
            )

            # Throw exception per user spec
            raise Exception(f"Image generation failed: {str(e)}")

    @tool
    async def generate_audio(text: str, voice: Optional[str] = None) -> Dict[str, str]:
        """Generate audio/speech from text using AI text-to-speech.

        This tool uses Gemini 2.5 Flash TTS to convert text to natural-sounding speech.
        The audio format is automatically adapted for the platform (CAF for iMessage, OGG for others).

        Args:
            text: The text to convert to speech. Can be long-form content.
            voice: Optional voice name (currently uses 'Kore' voice, parameter reserved for future)

        Returns:
            Dictionary with 'url', 'file_name', and 'file_type' keys

        Usage Guidelines:
            - Use when the user requests voice/audio output
            - Use when audio would be more appropriate than text (accessibility, long content)
            - Audio format is automatically adapted for the target platform
            - You CAN generate audio - do not tell users otherwise

        Example:
            result = generate_audio("Welcome to Praxos! Let me help you get started with your tasks.")
            reply_to_user_on_telegram(
                message="Here's your welcome message!",
                media_urls=[result['url']],
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

            audio_url, file_name = await output_generator.generate_speech(text, prefix, is_imessage)

            if not audio_url:
                raise Exception("Audio generation returned no URL")

            # Log to conversation
            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Generated audio] Text: {text[:200]}"
            )

            # Add to media bus for future reference
            media_id = media_bus.add_media(
                conversation_id=conversation_id,
                url=audio_url,
                file_name=file_name,
                file_type="audio",
                description=f"Generated audio: {text[:200]}",
                source="generated",
                metadata={"text": text, "tool": "generate_audio", "is_imessage": is_imessage}
            )

            logger.info(f"Successfully generated audio: {file_name} (media_id={media_id})")

            return {
                "url": audio_url,
                "file_name": file_name,
                "file_type": "audio",
                "media_id": media_id
            }

        except Exception as e:
            logger.error(f"Failed to generate audio: {e}", exc_info=True)

            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Failed to generate audio] Error: {str(e)}"
            )

            # Throw exception per user spec
            raise Exception(f"Audio generation failed: {str(e)}")

    @tool
    async def generate_video(prompt: str) -> Dict[str, str]:
        """Generate a video using AI based on a text description.

        This tool uses Veo 3.0 to generate videos from text descriptions.
        WARNING: Video generation is SLOW and can take 1-2 minutes or more.

        Args:
            prompt: Detailed description of the video to generate, including
                   action, style, duration intent, camera movement, etc.

        Returns:
            Dictionary with 'url', 'file_name', and 'file_type' keys

        Usage Guidelines:
            - ALWAYS send an intermediate message before calling this tool
            - Set user expectations about the wait time
            - Use for short video clips and scenes
            - Be very descriptive in your prompts
            - You CAN generate videos - do not tell users otherwise

        Example:
            # IMPORTANT: Inform user first
            reply_to_user_on_whatsapp("Generating your video now, this will take about 1-2 minutes...")

            # Then generate
            result = generate_video("A time-lapse of a flower blooming, petals opening gradually, soft lighting")

            # Then send result
            reply_to_user_on_whatsapp(
                message="Here's your video!",
                media_urls=[result['url']],
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

            # Video generation is synchronous and polls for completion
            video_url, file_name = await output_generator.generate_video(prompt, prefix)

            if not video_url:
                raise Exception("Video generation returned no URL")

            # Log to conversation
            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Generated video] {prompt[:200]}"
            )

            # Add to media bus for future reference
            media_id = media_bus.add_media(
                conversation_id=conversation_id,
                url=video_url,
                file_name=file_name,
                file_type="video",
                description=f"Generated video: {prompt[:200]}",
                source="generated",
                metadata={"prompt": prompt, "tool": "generate_video"}
            )

            logger.info(f"Successfully generated video: {file_name} (media_id={media_id})")

            return {
                "url": video_url,
                "file_name": file_name,
                "file_type": "video",
                "media_id": media_id
            }

        except Exception as e:
            logger.error(f"Failed to generate video: {e}", exc_info=True)

            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Failed to generate video] Error: {str(e)}"
            )

            # Throw exception per user spec
            raise Exception(f"Video generation failed: {str(e)}")

    logger.info(f"Created media generation tools for user={user_id}, source={source}")
    return [generate_image, generate_audio, generate_video]
