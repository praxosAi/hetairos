from google import genai
from google.genai import types
from src.config.settings import settings
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

# Cache name is now loaded from Redis at runtime
# To regenerate: system automatically detects YAML changes and regenerates
PLANNING_CACHE_NAME = None  # Will be loaded from Redis on first use


async def get_planning_cache_name() -> str:
    """
    Get the current Gemini planning cache name from Redis.
    Triggers cache creation if not found.

    Returns:
        str: Cache name to use with Gemini
    """
    from src.services.ai_service.prompts.cache_manager import get_gemini_planning_cache_name

    cache_name = await get_gemini_planning_cache_name()

    if not cache_name:
        logger.error("Failed to get Gemini planning cache name from Redis")
        # Fallback: use None (Gemini will work without cache, just slower)
        return None

    return cache_name


async def update_cache_ttl():
    """Updates the cache TTL in a fire-and-forget manner."""
    try:
        cache_name = await get_planning_cache_name()
        if not cache_name:
            logger.warning("No cache name available, skipping TTL update")
            return

        logger.info(f"Starting cache TTL update for {cache_name}")
        client_gemini = genai.Client(api_key=settings.GEMINI_API_KEY)
        await client_gemini.aio.caches.update(
            name=cache_name,
            config=types.UpdateCachedContentConfig(
                ttl='86400s'
            )
        )
        logger.info(f"Successfully updated cache TTL for {cache_name} to 86400 seconds (24 hours)")
    except Exception as e:
        logger.error(f"Failed to update cache TTL: {e}", exc_info=True)