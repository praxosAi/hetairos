"""
Google Places search tool with ToolExecutionResponse wrapper.
"""

from langchain_core.tools import tool
from langchain_community.tools import GooglePlacesTool as LangchainGooglePlacesTool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)


def create_google_places_tools():
    """
    Creates Google Places tool wrapped in ToolExecutionResponse format.
    Requires GPLACES_API_KEY environment variable.
    """

    @tool
    def GooglePlacesTool(query: str) -> ToolExecutionResponse:
        """
        Search for places, businesses, restaurants, and locations using Google Places API.
        Returns information about addresses, phone numbers, ratings, and more.

        Args:
            query: Search query (e.g., "coffee shops near me", "Pizza Hut in New York", "restaurants in Times Square")

        Examples:
            - GooglePlacesTool("sushi restaurants in Manhattan")
            - GooglePlacesTool("gas stations near Central Park")
            - GooglePlacesTool("hotels in San Francisco")
            - GooglePlacesTool("Apple Store locations")

        Returns:
            ToolExecutionResponse with place details including name, address, rating, phone, etc.
        """
        logger.info(f"Searching Google Places for: {query}")

        try:
            # Initialize the langchain GooglePlacesTool
            places_tool = LangchainGooglePlacesTool()

            # Run the search
            result = places_tool.run(query)

            logger.info(f"Google Places search completed for query: {query}")

            return ToolExecutionResponse(
                status="success",
                result=result
            )

        except Exception as e:
            logger.error(f"Error searching Google Places: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="GooglePlacesTool",
                exception=e,
                integration="Google Places API",
                context={"query": query}
            )

    return [GooglePlacesTool]
