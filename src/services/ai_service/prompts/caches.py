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
    """
    Updates the cache TTL in a fire-and-forget manner.
    Also updates Redis key TTL to match.
    """
    EXTENDED_TTL = 86400  # 24 hours

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
                ttl=f'{EXTENDED_TTL}s'
            )
        )
        logger.info(f"Successfully updated Gemini cache TTL for {cache_name} to {EXTENDED_TTL} seconds (24 hours)")

        # Also update Redis key TTL to match
        from src.utils.redis_client import redis_client
        from src.services.ai_service.prompts.cache_manager import GEMINI_CACHE_NAME_KEY

        await redis_client.expire(GEMINI_CACHE_NAME_KEY, EXTENDED_TTL)
        logger.info(f"Updated Redis cache_name TTL to {EXTENDED_TTL} seconds (24 hours)")

    except Exception as e:
        logger.error(f"Failed to update cache TTL: {e}", exc_info=True)