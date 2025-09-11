import redis.asyncio as redis
import logging
from src.config.settings import settings
from src.utils.logging import setup_logger
logger = setup_logger(__name__)

class RedisClient:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            if not settings.REDIS_URL or not settings.REDIS_PASSWORD:
                raise ValueError("REDIS_URL and REDIS_PASSWORD must be set in the environment.")
            
            logger.info(f"Creating new Redis client instance for host: {settings.REDIS_URL}")
            try:
                cls._instance = redis.Redis(
                    host=settings.REDIS_URL,
                    port=6380,  # Default SSL port for Azure Cache for Redis
                    password=settings.REDIS_PASSWORD,
                    ssl=True,
                    decode_responses=True  # Decode responses to UTF-8 by default
                )
                logger.info("Redis client instance created successfully.")
            except Exception as e:
                logger.error(f"Failed to create Redis client: {e}", exc_info=True)
                raise
        return cls._instance

# Singleton instance for easy access
redis_client = RedisClient.get_instance()

async def publish_message(channel: str, message: str):
    """Publishes a message to a Redis channel."""
    try:
        await redis_client.publish(channel, message)
        logger.info(f"Published message to channel '{channel}': {message}")
    except Exception as e:
        logger.error(f"Failed to publish message to Redis channel '{channel}': {e}", exc_info=True)

async def subscribe_to_channel(channel: str):
    """Subscribes to a Redis channel and returns a pubsub object."""
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to Redis channel '{channel}'")
        return pubsub
    except Exception as e:
        logger.error(f"Failed to subscribe to Redis channel '{channel}': {e}", exc_info=True)
        raise
