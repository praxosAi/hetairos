import requests
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from src.config.settings import settings

logger = setup_logger(__name__)
API_KEY = settings.WEATHER_API_KEY

@tool
def get_weather_forecast(latitude: float, longitude: float) -> ToolExecutionResponse:
    """
    Get weather forecast and current conditions using precise coordinates.
    Requires coordinates from google_places_text_search.

    Args:
        latitude: Latitude coordinate (e.g., 43.6394)
        longitude: Longitude coordinate (e.g., -79.4198)

    Returns:
        Full weather forecast with current conditions and multi-day forecast
    """
    try:
        # Format coordinates as "lat,lng" for WeatherAPI
        coordinates = f"{latitude},{longitude}"

        url = "http://api.weatherapi.com/v1/forecast.json"
        params = {
            "key": API_KEY,
            "q": coordinates
        }

        logger.info(f"Fetching weather forecast for coordinates: {coordinates}")
        response = requests.get(url, params=params, timeout=15)

        # Handle rate limiting
        if response.status_code == 429:
            logger.warning("WeatherAPI rate limit exceeded")
            return ErrorResponseBuilder.rate_limit(
                operation="get_weather_forecast"
            )

        response.raise_for_status()
        data = response.json()

        return ToolExecutionResponse(
            status="success",
            result=data
        )

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            try:
                error_data = e.response.json().get("error", {})
                error_msg = error_data.get("message", str(e))
            except:
                error_msg = str(e)

            return ErrorResponseBuilder.invalid_parameter(
                operation="get_weather_forecast",
                param_name="coordinates",
                param_value=f"{latitude},{longitude}",
                expected_format="Valid latitude and longitude coordinates",
                validation_error=error_msg
            )

        logger.error(f"HTTP error fetching weather: {e}", exc_info=True)
        return ErrorResponseBuilder.from_exception(
            operation="get_weather_forecast",
            exception=e,
            integration="WeatherAPI",
            context={"latitude": latitude, "longitude": longitude}
        )

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching weather for coordinates: {latitude},{longitude}")
        return ErrorResponseBuilder.from_exception(
            operation="get_weather_forecast",
            exception=Exception("Request timeout"),
            integration="WeatherAPI",
            context={"latitude": latitude, "longitude": longitude, "error": "Request timed out after 15 seconds"}
        )

    except Exception as e:
        logger.error(f"Error fetching weather: {e}", exc_info=True)
        return ErrorResponseBuilder.from_exception(
            operation="get_weather_forecast",
            exception=e,
            integration="WeatherAPI",
            context={"latitude": latitude, "longitude": longitude}
        )

def create_weather_tools(tool_registry) -> list:
    """
    Create weather tool for WeatherAPI.com.
    Requires coordinates from google_places_text_search.
    """
    tools = [get_weather_forecast]
    tool_registry.apply_descriptions_to_tools(tools)
    logger.info("Created weather tool")
    return tools
