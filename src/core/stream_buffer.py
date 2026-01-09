from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import json
from src.utils.logging import setup_logger

logger = setup_logger(__name__)


class StreamBuffer(ABC):
    """Abstract interface for streaming events"""

    @abstractmethod
    async def write(self, event: Dict) -> None:
        """Write event to buffer"""
        pass


class NoOpStreamBuffer(StreamBuffer):
    """Buffer that discards all events (batch mode)"""

    async def write(self, event: Dict) -> None:
        # Silently discard
        pass


class RedisStreamBuffer(StreamBuffer):
    """Buffer that publishes events to Redis channel"""

    def __init__(self, redis_channel: str):
        self.channel = redis_channel
        logger.info(f"RedisStreamBuffer initialized for channel: {redis_channel}")

    async def write(self, event: Dict) -> None:
        from src.utils.redis_client import redis_client
        try:
            await redis_client.publish(self.channel, json.dumps(event))
        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}", exc_info=True)


class CollectingStreamBuffer(StreamBuffer):
    """Buffer that collects events for testing/debugging"""

    def __init__(self):
        self.events: List[Dict] = []

    async def write(self, event: Dict) -> None:
        self.events.append(event)
