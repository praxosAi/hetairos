"""
Google Cloud Vision API client for image analysis.
Provides product/brand recognition without CAPTCHA issues.
"""

from typing import Dict, Any, List, Optional
import asyncio
from google.cloud import vision
from src.utils.logging import setup_logger

logger = setup_logger(__name__)


class GoogleVisionClient:
    """Client for Google Cloud Vision API using service account credentials."""

    def __init__(self):
        """Initialize Google Vision client."""
        self.client = None

    async def authenticate(self) -> bool:
        """
        Authenticate with Google Cloud Vision API.
        Uses GOOGLE_APPLICATION_CREDENTIALS environment variable.

        Returns:
            True if authentication successful
        """
        try:
            self.client = vision.ImageAnnotatorClient()
            logger.info("Google Vision authenticated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate Google Vision: {e}", exc_info=True)
            return False

    async def analyze_image_from_url(
        self,
        image_url: str,
        detect_logos: bool = True,
        detect_web: bool = True,
        detect_labels: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze an image from URL using google-cloud-vision library (works with Azure Blob SAS URLs).

        Args:
            image_url: Public URL to image
            detect_logos: Detect brand logos
            detect_web: Find similar products online
            detect_labels: Detect objects/scenes

        Returns:
            Dictionary with detection results
        """
        if not self.client:
            raise Exception("Not authenticated. Call authenticate() first.")

        try:
            # Create image from URL
            image = vision.Image()
            image.source.image_uri = image_url

            results = {}

            # Run detections in thread pool (library is synchronous)
            loop = asyncio.get_event_loop()

            # Logo detection
            if detect_logos:
                response = await loop.run_in_executor(None, lambda: self.client.logo_detection(image=image))
                results['logos'] = [
                    {'brand': logo.description, 'confidence': logo.score}
                    for logo in response.logo_annotations
                ]

            # Web detection
            if detect_web:
                response = await loop.run_in_executor(None, lambda: self.client.web_detection(image=image))
                web_detection = response.web_detection
                results['web'] = {
                    'product_match': [label.label for label in web_detection.best_guess_labels],
                    'shopping_links': [
                        {'title': page.page_title, 'url': page.url}
                        for page in web_detection.pages_with_matching_images[:5]
                    ],
                    'similar_images': [
                        img.url for img in web_detection.visually_similar_images[:5]
                    ]
                }

            # Label detection
            if detect_labels:
                response = await loop.run_in_executor(None, lambda: self.client.label_detection(image=image))
                results['labels'] = [
                    {'description': label.description, 'confidence': label.score}
                    for label in response.label_annotations[:10]
                ]

            logger.info("Image analysis completed")
            return results

        except Exception as e:
            logger.error(f"Error analyzing image: {e}", exc_info=True)
            raise
