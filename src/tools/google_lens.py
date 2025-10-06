"""
Product recognition tools using Google Cloud Vision API.
No CAPTCHA issues, works with any product image.
"""

from typing import Optional
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)


def create_google_lens_tools(vision_client):
    """
    Creates product recognition tools using Google Cloud Vision API.

    Args:
        vision_client: Authenticated GoogleVisionClient instance
    """

    @tool
    async def identify_product_in_image(
        image_url: str
    ) -> ToolExecutionResponse:
        """
        Identify products, brands, and objects in an image using Google Vision AI.
        Perfect for identifying shoe brands, clothing items, products, logos, etc.

        Works with Azure Blob SAS URLs - fast and reliable, no CAPTCHA.

        Args:
            image_url: Public URL to the image (e.g., Azure Blob SAS URL from conversation context)

        Examples:
            - identify_product_in_image("https://blob.../shoe.jpg")
            - identify_product_in_image("https://blob.../clothing.jpg")
            - identify_product_in_image("https://blob.../gadget.jpg")
        """
        logger.info(f"Identifying product in image: {image_url}")

        try:
            # Analyze image with logo, web, and label detection
            results = await vision_client.analyze_image_from_url(
                image_url,
                detect_logos=True,
                detect_web=True,
                detect_labels=True
            )

            # Format results for user
            summary = []

            # Brand/logo detection (most important for products)
            if results.get('logos'):
                brands = [f"{logo['brand']} ({logo['confidence']:.0%})" for logo in results['logos']]
                summary.append(f"**Brand detected**: {', '.join(brands)}")

            # Web detection - what is this product?
            if results.get('web', {}).get('product_match'):
                product_names = results['web']['product_match']
                summary.append(f"**Product**: {', '.join(product_names)}")

            # Shopping links
            if results.get('web', {}).get('shopping_links'):
                links = [f"- {link['title']}: {link['url']}"
                        for link in results['web']['shopping_links'][:3]]
                if links:
                    summary.append(f"**Where to buy**:\n" + '\n'.join(links))

            # Object labels (fallback if no brand detected)
            if results.get('labels') and not results.get('logos'):
                objects = [f"{label['description']} ({label['confidence']:.0%})"
                          for label in results['labels'][:5]]
                summary.append(f"**Objects detected**: {', '.join(objects)}")

            formatted_result = "\n\n".join(summary) if summary else "Unable to identify specific brand or product in the image."

            logger.info("Product identification completed")

            return ToolExecutionResponse(
                status="success",
                result=formatted_result
            )

        except Exception as e:
            logger.error(f"Error identifying product: {e}", exc_info=True)
            return ToolExecutionResponse(
                status="error",
                system_error=str(e),
                user_message="Failed to analyze the image. Please ensure the image URL is accessible."
            )

    return [identify_product_in_image]
