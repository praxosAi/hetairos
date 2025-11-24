"""
Google Places tools suite with ToolExecutionResponse wrapper.
Uses Google Places Web Service API.

Available endpoints:
- Text Search: Search for places based on text query
- Nearby Search: Search for places within a specified area by type
- Find Place: Find a specific place by name, phone, or address
- Place Details: Get detailed information about a specific place
"""

from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
import os
import requests
from typing import Optional

logger = setup_logger(__name__)


def create_google_places_tools(tool_registry, tool_names=None):
    """
    Creates Google Places tools wrapped in ToolExecutionResponse format.
    Requires GPLACES_API_KEY environment variable.

    Args:
        tool_registry: Tool registry for applying YAML descriptions
        tool_names: Optional list of specific tool names to create.
                   If None, creates all tools.
                   Valid names: 'google_places_text_search', 'google_places_nearby_search',
                               'google_places_find_place', 'google_places_get_details'
    """

    @tool
    def google_places_text_search(query: str, latitude: float = None, longitude: float = None, radius: int = 5000) -> ToolExecutionResponse:
        """
        Search for places using text query. Good for general searches like "pizza near me" or "Starbucks in Manhattan".

        IMPORTANT: If you have the user's location from get_user_location(), pass latitude and longitude!

        Args:
            query: Search query (e.g., "coffee shops", "Pizza Hut", "restaurants")
            latitude: Optional latitude for location-based search
            longitude: Optional longitude for location-based search
            radius: Search radius in meters (default 5000)

        Returns:
            ToolExecutionResponse with list of places
        """
        logger.info(f"Text search: {query} at {latitude},{longitude}")

        try:
            api_key = os.getenv("GPLACES_API_KEY")
            if not api_key:
                raise ValueError("GPLACES_API_KEY not set")

            url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            params = {"query": query, "key": api_key}

            if latitude is not None and longitude is not None:
                params["location"] = f"{latitude},{longitude}"
                params["radius"] = radius

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("status") not in ["OK", "ZERO_RESULTS"]:
                raise Exception(f"API error: {data.get('error_message', data.get('status'))}")

            results = data.get("results", [])
            if not results:
                return ToolExecutionResponse(status="success", result="No places found.")

            formatted = []
            for idx, place in enumerate(results[:10], 1):
                location = place.get("geometry", {}).get("location", {})
                formatted.append(
                    f"{idx}. {place.get('name', 'Unknown')}\n"
                    f"Address: {place.get('formatted_address', 'Unknown')}\n"
                    f"Coordinates: {location.get('lat', 'N/A')}, {location.get('lng', 'N/A')}\n"
                    f"Place ID: {place.get('place_id', 'Unknown')}\n"
                    f"Rating: {place.get('rating', 'N/A')} ({place.get('user_ratings_total', 0)} reviews)"
                )

            return ToolExecutionResponse(status="success", result="\n\n".join(formatted))

        except Exception as e:
            logger.error(f"Text search error: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="google_places_text_search",
                exception=e,
                integration="Google Places API",
                context={"query": query, "latitude": latitude, "longitude": longitude}
            )

    @tool
    def google_places_nearby_search(latitude: float, longitude: float, place_type: str = None, keyword: str = None, radius: int = 5000) -> ToolExecutionResponse:
        """
        Search for places near a specific location by type or keyword. Best for "find X near me" queries.

        Args:
            latitude: Latitude of center point (required)
            longitude: Longitude of center point (required)
            place_type: Type of place (e.g., "restaurant", "cafe", "gas_station", "hospital", "atm")
            keyword: Keyword to match (e.g., "pizza", "vegetarian", "24 hour")
            radius: Search radius in meters (default 5000, max 50000)

        Common types: restaurant, cafe, bar, gym, hospital, pharmacy, bank, atm, gas_station,
                     parking, grocery_or_supermarket, shopping_mall, hotel, airport

        Examples:
            - google_places_nearby_search(40.7128, -74.0060, place_type="restaurant")
            - google_places_nearby_search(42.3601, -71.0589, keyword="coffee", radius=1000)

        Returns:
            ToolExecutionResponse with list of nearby places
        """
        logger.info(f"Nearby search: type={place_type}, keyword={keyword} at {latitude},{longitude}")

        try:
            api_key = os.getenv("GPLACES_API_KEY")
            if not api_key:
                raise ValueError("GPLACES_API_KEY not set")

            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                "location": f"{latitude},{longitude}",
                "radius": min(radius, 50000),  # API max is 50km
                "key": api_key
            }

            if place_type:
                params["type"] = place_type
            if keyword:
                params["keyword"] = keyword

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("status") not in ["OK", "ZERO_RESULTS"]:
                raise Exception(f"API error: {data.get('error_message', data.get('status'))}")

            results = data.get("results", [])
            if not results:
                return ToolExecutionResponse(status="success", result="No places found nearby.")

            formatted = []
            for idx, place in enumerate(results[:10], 1):
                types = ", ".join(place.get("types", [])[:3])
                open_now = "Open now" if place.get("opening_hours", {}).get("open_now") else "Closed" if "opening_hours" in place else "Unknown"

                formatted.append(
                    f"{idx}. {place.get('name', 'Unknown')} [{open_now}]\n"
                    f"Address: {place.get('vicinity', 'Unknown')}\n"
                    f"Types: {types}\n"
                    f"Place ID: {place.get('place_id', 'Unknown')}\n"
                    f"Rating: {place.get('rating', 'N/A')} ({place.get('user_ratings_total', 0)} reviews)"
                )

            return ToolExecutionResponse(status="success", result="\n\n".join(formatted))

        except Exception as e:
            logger.error(f"Nearby search error: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="google_places_nearby_search",
                exception=e,
                integration="Google Places API",
                context={"latitude": latitude, "longitude": longitude, "type": place_type, "keyword": keyword}
            )

    @tool
    def google_places_find_place(input_text: str, input_type: str = "textquery") -> ToolExecutionResponse:
        """
        Find a specific place by name, phone number, or address. Returns the best match.

        Args:
            input_text: The text to search (name, phone, or address)
            input_type: Type of input - "textquery" for names/addresses or "phonenumber" for phone numbers

        Examples:
            - google_places_find_place("Museum of Modern Art New York")
            - google_places_find_place("Eiffel Tower")
            - google_places_find_place("+1 212-708-9400", input_type="phonenumber")

        Returns:
            ToolExecutionResponse with the matching place details
        """
        logger.info(f"Find place: {input_text} (type: {input_type})")

        try:
            api_key = os.getenv("GPLACES_API_KEY")
            if not api_key:
                raise ValueError("GPLACES_API_KEY not set")

            url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
            params = {
                "input": input_text,
                "inputtype": input_type,
                "fields": "name,formatted_address,place_id,rating,user_ratings_total,opening_hours,geometry",
                "key": api_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("status") not in ["OK", "ZERO_RESULTS"]:
                raise Exception(f"API error: {data.get('error_message', data.get('status'))}")

            candidates = data.get("candidates", [])
            if not candidates:
                return ToolExecutionResponse(status="success", result="No place found matching your query.")

            # Return the top match
            place = candidates[0]
            open_now = "Open now" if place.get("opening_hours", {}).get("open_now") else "Closed" if "opening_hours" in place else "Unknown"
            location = place.get("geometry", {}).get("location", {})

            result = (
                f"Found: {place.get('name', 'Unknown')} [{open_now}]\n"
                f"Address: {place.get('formatted_address', 'Unknown')}\n"
                f"Location: {location.get('lat', 'N/A')}, {location.get('lng', 'N/A')}\n"
                f"Place ID: {place.get('place_id', 'Unknown')}\n"
                f"Rating: {place.get('rating', 'N/A')} ({place.get('user_ratings_total', 0)} reviews)"
            )

            return ToolExecutionResponse(status="success", result=result)

        except Exception as e:
            logger.error(f"Find place error: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="google_places_find_place",
                exception=e,
                integration="Google Places API",
                context={"input_text": input_text, "input_type": input_type}
            )

    @tool
    def google_places_get_details(place_id: str) -> ToolExecutionResponse:
        """
        Get detailed information about a specific place using its Place ID.
        Use this after getting a place_id from other search tools.

        Args:
            place_id: The Google Place ID (from text_search, nearby_search, or find_place results)

        Returns:
            ToolExecutionResponse with detailed place information including hours, phone, website, photos, etc.
        """
        logger.info(f"Get details for place_id: {place_id}")

        try:
            api_key = os.getenv("GPLACES_API_KEY")
            if not api_key:
                raise ValueError("GPLACES_API_KEY not set")

            url = "https://maps.googleapis.com/maps/api/place/details/json"
            params = {
                "place_id": place_id,
                "fields": "name,formatted_address,formatted_phone_number,international_phone_number,website,rating,user_ratings_total,price_level,opening_hours,geometry,types,reviews",
                "key": api_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK":
                raise Exception(f"API error: {data.get('error_message', data.get('status'))}")

            place = data.get("result", {})

            # Format opening hours
            opening_hours = place.get("opening_hours", {})
            hours_text = "\n".join(opening_hours.get("weekday_text", ["Not available"]))
            open_now = "Yes" if opening_hours.get("open_now") else "No" if "open_now" in opening_hours else "Unknown"

            # Format price level
            price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
            price = price_map.get(place.get("price_level"), "N/A")

            # Get location
            location = place.get("geometry", {}).get("location", {})

            # Format reviews (top 3)
            reviews = place.get("reviews", [])[:3]
            reviews_text = ""
            if reviews:
                reviews_text = "\n\nTop Reviews:\n" + "\n".join([
                    f"- {r.get('author_name')}: {r.get('rating')}/5 - \"{r.get('text', '')[:100]}...\""
                    for r in reviews
                ])

            result = (
                f"{place.get('name', 'Unknown')}\n"
                f"{'=' * 50}\n"
                f"Address: {place.get('formatted_address', 'Unknown')}\n"
                f"Phone: {place.get('formatted_phone_number', place.get('international_phone_number', 'Not available'))}\n"
                f"Website: {place.get('website', 'Not available')}\n"
                f"Location: {location.get('lat', 'N/A')}, {location.get('lng', 'N/A')}\n"
                f"Rating: {place.get('rating', 'N/A')}/5 ({place.get('user_ratings_total', 0)} reviews)\n"
                f"Price Level: {price}\n"
                f"Open Now: {open_now}\n"
                f"Types: {', '.join(place.get('types', []))}\n"
                f"\nHours:\n{hours_text}"
                f"{reviews_text}"
            )

            return ToolExecutionResponse(status="success", result=result)

        except Exception as e:
            logger.error(f"Get details error: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="google_places_get_details",
                exception=e,
                integration="Google Places API",
                context={"place_id": place_id}
            )

    all_tools = {
        'google_places_text_search': google_places_text_search,
        'google_places_nearby_search': google_places_nearby_search,
        'google_places_find_place': google_places_find_place,
        'google_places_get_details': google_places_get_details
    }

    # Filter tools based on tool_names parameter
    if tool_names is None:
        # Return all tools if no specific tools requested
        selected_tools = list(all_tools.values())
    else:
        # Return only the requested tools
        selected_tools = [all_tools[name] for name in tool_names if name in all_tools]

    tool_registry.apply_descriptions_to_tools(selected_tools)
    return selected_tools
