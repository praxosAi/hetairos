from google import genai
from google.genai import types
from src.config.settings import settings
from src.utils.logging import setup_logger
logger = setup_logger(__name__)
PLANNING_CACHE_NAME = 'cachedContents/bzft7d0tw1kfmr0or2ttyj4e730zwr1278uf2m9w'
async def update_cache_ttl():
    """Updates the cache TTL in a fire-and-forget manner."""
    try:
        logger.info(f"Starting cache TTL update for {PLANNING_CACHE_NAME}")
        client_gemini = genai.Client(api_key=settings.GEMINI_API_KEY)
        await client_gemini.aio.caches.update(
            name=PLANNING_CACHE_NAME,
            config=types.UpdateCachedContentConfig(
                ttl='86400s'
            )
        )
        logger.info(f"Successfully updated cache TTL for {PLANNING_CACHE_NAME} to 86400 seconds (24 hours)")
    except Exception as e:
        logger.error(f"Failed to update cache TTL for {PLANNING_CACHE_NAME}: {e}", exc_info=True)
    ## on startup, check if the cache exists, if not create it