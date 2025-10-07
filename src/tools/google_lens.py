"""
Product recognition tools using SerpAPI Google Lens.
No CAPTCHA, no service account setup - just an API key.
"""

from langchain_core.tools import tool
from langchain_community.tools.google_lens import GoogleLensQueryRun
from langchain_community.utilities.google_lens import GoogleLensAPIWrapper
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
import os

logger = setup_logger(__name__)


def create_google_lens_tools():
    """
    Creates Google Lens tools using SerpAPI.
    Requires SERPAPI_API_KEY environment variable.
    """

    @tool
    async def identify_product_in_image(image_url: str) -> ToolExecutionResponse:
        """
        Identify products, brands, and objects in an image using Google Lens via SerpAPI.
        Perfect for identifying shoe brands, clothing items, products, logos, etc.

        Works with Azure Blob SAS URLs - fast and reliable, no CAPTCHA.

        Args:
            image_url: Public URL to the image (e.g., Azure Blob SAS URL from conversation context)

        Examples:
            - identify_product_in_image("https://blob.../shoe.jpg")
            - identify_product_in_image("https://blob.../clothing.jpg")
            - identify_product_in_image("https://blob.../gadget.jpg")
        """
        logger.info(f"Identifying product in image with Google Lens: {image_url}")

        try:
            # Initialize SerpAPI Google Lens wrapper
            api_wrapper = GoogleLensAPIWrapper()

            # Run Google Lens analysis
            result = api_wrapper.run(image_url)

            logger.info("Google Lens product identification completed")

            return ToolExecutionResponse(
                status="success",
                result=result
            )

        except Exception as e:
            logger.error(f"Error identifying product with Google Lens: {e}", exc_info=True)
            return ToolExecutionResponse(
                status="error",
                system_error=str(e),
                user_message="Failed to analyze the image with Google Lens. Please ensure the image URL is accessible."
            )

    return [identify_product_in_image]
