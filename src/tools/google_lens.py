"""
Google Lens tools using direct URL access + browser automation.
Simpler alternative to Google Cloud Vision API - no credentials needed!
"""

from typing import Optional
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from src.config.settings import settings

logger = setup_logger(__name__)


def create_google_lens_tools(request_id: str):
    """
    Creates Google Lens tools using browser automation.

    Args:
        request_id: Request ID for tracing
    """

    @tool
    async def search_image_with_google_lens(
        image_url: str,
        search_type: str = "products"
    ) -> ToolExecutionResponse:
        """
        Search for an image using Google Lens to identify products, brands, similar items, or text.
        Perfect for identifying shoe brands, clothing items, products, logos, landmarks, etc.

        IMPORTANT: This takes 30-60 seconds. Use send_intermediate_message first to notify the user.

        Args:
            image_url: Public URL to the image (e.g., Azure Blob SAS URL from conversation context)
            search_type: What to search for:
                - "products" (default) - Find products, brands, where to buy
                - "text" - Extract and translate text from image
                - "similar" - Find visually similar images
                - "all" - All available information

        Examples:
            - search_image_with_google_lens("https://blob.../shoe.jpg", "products")
            - search_image_with_google_lens("https://blob.../receipt.jpg", "text")
            - search_image_with_google_lens("https://blob.../painting.jpg", "similar")
        """
        logger.info(f"Google Lens search for image: {image_url}, type: {search_type}")

        try:
            from browser_use import Agent, ChatOpenAI
            from urllib.parse import quote

            # URL-encode the image URL to handle SAS query parameters properly
            encoded_image_url = quote(image_url, safe='')

            # Construct Google Lens URL with properly encoded image URL
            lens_url = f"https://lens.google.com/uploadbyurl?url={encoded_image_url}"

            logger.info(f"Encoded Lens URL: {lens_url}")

            # Create task based on search type
            task_descriptions = {
                "products": "Navigate to this Google Lens page and extract: 1) Brand/product name, 2) Product details, 3) Where to buy (shopping links). Focus on identifying the brand.",
                "text": "Navigate to this Google Lens page and extract all readable text from the image using the Text tab.",
                "similar": "Navigate to this Google Lens page and find visually similar images and where they appear online.",
                "all": "Navigate to this Google Lens page and extract all available information: products, text, similar images, and any other relevant data."
            }

            task = f"{task_descriptions.get(search_type, task_descriptions['products'])} URL: {lens_url}"

            # Use browser-use with same Portkey config as main agent
            portkey_headers = {
                'x-portkey-api-key': settings.PORTKEY_API_KEY,
                'x-portkey-provider': 'azure-openai',
                'x-portkey-trace-id': f"{request_id}_googlelens"
            }
            portkey_llm = ChatOpenAI(
                model='@azureopenai/gpt-5-mini',
                default_headers=portkey_headers,
                base_url='https://api.portkey.ai/v1',
                api_key=settings.PORTKEY_API_KEY
            )

            browser_agent = Agent(
                task=task,
                llm=portkey_llm,
                use_vision=True
            )

            # Execute browsing task
            result = await browser_agent.run(max_steps=20)

            logger.info(f"Google Lens search completed for {image_url}")

            return ToolExecutionResponse(
                status="success",
                result=str(result)
            )

        except Exception as e:
            logger.error(f"Error in Google Lens search: {e}", exc_info=True)
            return ToolExecutionResponse(
                status="error",
                system_error=str(e),
                user_message="Failed to search with Google Lens. The image may not be accessible or the service is unavailable."
            )

    return [search_image_with_google_lens]
