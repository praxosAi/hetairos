"""
Cache Manager for Tool Documentation.

Manages Gemini cache invalidation based on tool YAML changes.
Uses Redis distributed lock to ensure only one pod regenerates cache.
"""

import asyncio
from typing import Optional
from src.utils.logging import setup_logger
from src.utils.redis_client import redis_client
from src.services.ai_service.prompts.granular_tooling_capabilities import get_tool_docs_hash

logger = setup_logger(__name__)

TOOL_DOCS_HASH_KEY = "praxos:tool_docs_hash"
GEMINI_CACHE_NAME_KEY = "praxos:gemini_planning_cache_name"
CACHE_REGENERATION_LOCK_KEY = "praxos:cache_regeneration_lock"
LOCK_TIMEOUT = 120  # 2 minutes
GEMINI_CACHE_TTL = 1200  # 20 minutes (must match Gemini cache TTL)


async def _regenerate_gemini_planning_cache() -> str:
    """
    Regenerate Gemini cached content for planning prompt.

    Returns:
        str: Cache name if successful, None otherwise
    """
    try:
        import os
        from google import genai
        from google.genai import types
        from src.services.ai_service.prompts.granular_tooling_capabilities import GRANULAR_TOOLING_CAPABILITIES
        from src.services.ai_service.ai_service_models import GranularPlanningResponse

        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not set")
            return None

        client_gemini = genai.Client(api_key=GEMINI_API_KEY)

        # Create function declaration for Gemini
        function_granular_planning_response = types.FunctionDeclaration(
            name='Create_Granular_Planning_Response',
            description='Create a granular planning response for the user query, specifying exact tool function IDs needed.',
            parameters_json_schema=GranularPlanningResponse.model_json_schema()
        )

        tool = types.Tool(function_declarations=[function_granular_planning_response])

        # Create cached content
        cache_result = client_gemini.caches.create(
            model="gemini-3-flash-preview",
            config=types.CreateCachedContentConfig(
                display_name='praxos_planning_prompt',
                system_instruction=(
                    """
                    You are an expert task planner with deep knowledge of available tools.
                    **Your goal:** Analyze the user's request and determine:
                      1. **Query Type**: Is this a 'command' (task to execute) or 'conversational' (no action needed)?
                      2. **Tooling Need**: Does this require any tools, or can it be answered conversationally?
                      3. **Required Tools**: If tools are needed, specify EXACTLY which tool function IDs are required. Be precise and minimal. Specify them in order of use.
                      4. Use intermediate messaging tool to first send a confirmation message to the user when the task involves long operations (30+ seconds), such as browsing websites, identifying products in images, or generating videos. then, proceed with the main tool, and finally, use the appropriate messaging tool to send the final response.
                      **CRITICAL**: Only include tools that are ACTUALLY needed for THIS specific task. Don't include tools "just in case." However, consider tools that need to be used in tandem to accomplish the task.
                      **IMPORTANT**: If multiple tools are needed, list them all and explain how they work together to complete the task.
                      **IMPORTANT**: we do not consider capabilities such as "Transcribing the contents" of an image, 'Translating the contents' of an email, 'transcribing an audio file', or 'summarizing a document' as separate tools. These are capabilities that are part of the core AI functionality, and do not require a separate tool. The tools listed here are for external integrations, or for specific actions that require a distinct function call. Such capabilities can be handled by the AI directly, without needing to invoke a separate tool. These capabilities are always available, and you can always do them.

                    the tooling capabilities are detailed in the system prompt.
                    Consider the conversation context. If a task was just completed, the user might be responding conversationally.
                    """
                ),
                tools=[tool],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode='ANY')
                ),
                contents=[GRANULAR_TOOLING_CAPABILITIES],
                ttl=f"{GEMINI_CACHE_TTL}s",  # TTL in seconds
            )
        )

        cache_name = cache_result.name
        logger.info(f"Gemini cache created: {cache_name}")

        return cache_name

    except Exception as e:
        logger.error(f"Error regenerating Gemini cache: {e}", exc_info=True)
        return None


async def check_and_regenerate_cache_if_needed():
    """
    Check if tool documentation has changed and regenerate Gemini cache if needed.
    Uses distributed lock to ensure only one pod regenerates.

    Returns:
        bool: True if cache was regenerated, False otherwise
    """
    try:
        # Get current hash from YAML
        current_hash = get_tool_docs_hash()
        logger.info(f"Current tool docs hash: {current_hash}")

        # Get stored hash from Redis
        stored_hash = await redis_client.get(TOOL_DOCS_HASH_KEY)
        if stored_hash:
            stored_hash = stored_hash.decode() if isinstance(stored_hash, bytes) else stored_hash

        if stored_hash and stored_hash == current_hash:
            logger.info("Tool docs hash unchanged, cache is up to date")
            return False

        logger.info(f"Tool docs hash changed: {stored_hash} -> {current_hash}")
        logger.info("Attempting to acquire cache regeneration lock...")

        # Try to acquire distributed lock
        lock_acquired = await redis_client.set(
            CACHE_REGENERATION_LOCK_KEY,
            current_hash,
            nx=True,  # Only set if not exists
            ex=LOCK_TIMEOUT  # Expire after timeout
        )

        if not lock_acquired:
            logger.info("Another pod is already regenerating cache, waiting...")

            # Wait for other pod to finish (poll for hash update)
            for i in range(30):  # Wait up to 60 seconds
                await asyncio.sleep(5)
                updated_hash = await redis_client.get(TOOL_DOCS_HASH_KEY)
                if updated_hash:
                    updated_hash = updated_hash.decode() if isinstance(updated_hash, bytes) else updated_hash
                if updated_hash and updated_hash == current_hash:
                    logger.info("Cache regenerated by another pod")
                    return False

            logger.warning("Timeout waiting for cache regeneration by another pod")
            return False

        try:
            logger.info("Lock acquired, regenerating Gemini cache...")

            # Regenerate Gemini cache
            new_cache_name = await _regenerate_gemini_planning_cache()

            if new_cache_name:
                # Store cache name in Redis with TTL matching Gemini cache
                # When Gemini cache expires, Redis key auto-expires too
                await redis_client.set(GEMINI_CACHE_NAME_KEY, new_cache_name, ex=GEMINI_CACHE_TTL)
                logger.info(f"New Gemini cache created: {new_cache_name} (TTL: {GEMINI_CACHE_TTL}s)")

                # Update stored hash in Redis (no TTL - stays until next change)
                await redis_client.set(TOOL_DOCS_HASH_KEY, current_hash)
                logger.info(f"Updated tool docs hash in Redis: {current_hash}")

                return True
            else:
                logger.error("Failed to regenerate Gemini cache")
                return False

        finally:
            # Release lock
            await redis_client.delete(CACHE_REGENERATION_LOCK_KEY)
            logger.info("Released cache regeneration lock")

    except Exception as e:
        logger.error(f"Error in cache check/regeneration: {e}", exc_info=True)
        return False


async def get_current_tool_docs_version() -> str:
    """
    Get the current tool documentation version hash.

    Returns:
        str: Version hash or 'unknown'
    """
    try:
        stored_hash = await redis_client.get(TOOL_DOCS_HASH_KEY)
        if stored_hash:
            stored_hash = stored_hash.decode() if isinstance(stored_hash, bytes) else stored_hash
        return stored_hash if stored_hash else get_tool_docs_hash()
    except Exception as e:
        logger.error(f"Error getting tool docs version: {e}")
        return "unknown"


async def get_gemini_planning_cache_name() -> Optional[str]:
    """
    Get the current Gemini planning cache name from Redis.
    If not found, triggers cache regeneration.

    Returns:
        str: Cache name if available, None otherwise
    """
    try:
        cache_name = await redis_client.get(GEMINI_CACHE_NAME_KEY)

        if cache_name:
            # Handle both bytes and str from Redis
            cache_name = cache_name.decode() if isinstance(cache_name, bytes) else cache_name
            return cache_name

        # No cache found, trigger regeneration
        logger.info("No Gemini cache found in Redis, regenerating...")
        await check_and_regenerate_cache_if_needed()

        # Try again after regeneration
        cache_name = await redis_client.get(GEMINI_CACHE_NAME_KEY)
        if cache_name:
            cache_name = cache_name.decode() if isinstance(cache_name, bytes) else cache_name
        return cache_name

    except Exception as e:
        logger.error(f"Error getting Gemini cache name: {e}", exc_info=True)
        return None
