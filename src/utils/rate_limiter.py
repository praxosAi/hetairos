from datetime import datetime, timedelta
from typing import Dict, DefaultDict, Optional
from collections import defaultdict
from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)

class RateLimiter:
    """
    Rate limiter using Redis for distributed rate limiting across pods.
    Falls back to in-memory for local development.
    """

    def __init__(self):
        # In-memory fallback for local dev
        self.usage_counts = defaultdict(lambda: defaultdict(int))
        self.reset_times = defaultdict(lambda: defaultdict(lambda: datetime.utcnow()))
        self.use_redis = False
        self.redis_client = None

        # Try to use Redis for distributed rate limiting
        try:
            from src.utils.redis_client import redis_client
            if redis_client:
                self.redis_client = redis_client
                self.use_redis = True
                logger.info("Rate limiter using Redis (distributed)")
        except Exception as e:
            logger.warning(f"Redis not available for rate limiting: {e}. Using in-memory (local only)")

    def check_limit(self, user_id: str, resource_type: str) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit for resource type.
        Returns (is_allowed, remaining_count)
        """
        limits = {
            "emails": settings.MAX_EMAILS,
            "email_attachments": settings.MAX_EMAIL_ATTACHMENTS,
            "whatsapp_messages": settings.MAX_WHATSAPP_MESSAGES,
            "telegram_messages": settings.MAX_WHATSAPP_MESSAGES,
            "gmail_webhooks": settings.MAX_GMAIL_WEBHOOKS_PER_HOUR,
            "gmail_history_calls": settings.MAX_HISTORY_CALLS_PER_HOUR,
            "http_requests": 1000,  # 1000 HTTP requests per hour per user
            "file_uploads": 100,    # 100 file uploads per hour per user
        }

        if resource_type not in limits:
            return True, float('inf')

        max_limit = limits[resource_type]

        if self.use_redis:
            return self._check_limit_redis(user_id, resource_type, max_limit)
        else:
            return self._check_limit_memory(user_id, resource_type, max_limit)

    def _check_limit_redis(self, user_id: str, resource_type: str, max_limit: int) -> tuple[bool, int]:
        """Redis-based rate limiting (works across pods)"""
        try:
            import asyncio

            # Key format: rate_limit:{user_id}:{resource_type}:{hour}
            # Using hour-based windows
            now = datetime.utcnow()
            hour_key = now.strftime('%Y%m%d%H')
            redis_key = f"rate_limit:{user_id}:{resource_type}:{hour_key}"

            # Run async Redis call in sync context
            async def get_count():
                count_str = await self.redis_client.get(redis_key)
                return int(count_str) if count_str else 0

            try:
                current_count = asyncio.run(get_count())
            except RuntimeError:
                # Already in async context
                loop = asyncio.get_event_loop()
                current_count = loop.run_until_complete(get_count())

            is_allowed = current_count < max_limit
            remaining = max_limit - current_count

            return is_allowed, remaining

        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}, allowing request")
            return True, max_limit  # Fail open

    def _check_limit_memory(self, user_id: str, resource_type: str, max_limit: int) -> tuple[bool, int]:
        """In-memory rate limiting (local dev only)"""
        current_count = self.usage_counts[user_id][resource_type]

        # Reset count if it's a new day (simple daily reset)
        now = datetime.utcnow()
        reset_time = self.reset_times[user_id][resource_type]

        # Handle case where reset_time might be default value
        if isinstance(reset_time, datetime) and now.date() > reset_time.date():
            self.usage_counts[user_id][resource_type] = 0
            self.reset_times[user_id][resource_type] = now
            current_count = 0
        elif not isinstance(reset_time, datetime):
            # Initialize reset time if not set properly
            self.reset_times[user_id][resource_type] = now

        is_allowed = current_count < max_limit
        remaining = max_limit - current_count

        return is_allowed, remaining

    def increment_usage(self, user_id: str, resource_type: str, count: int = 1):
        """Increment usage count for user and resource type"""
        if self.use_redis:
            self._increment_redis(user_id, resource_type, count)
        else:
            self._increment_memory(user_id, resource_type, count)

    def _increment_redis(self, user_id: str, resource_type: str, count: int):
        """Increment in Redis"""
        try:
            import asyncio

            now = datetime.utcnow()
            hour_key = now.strftime('%Y%m%d%H')
            redis_key = f"rate_limit:{user_id}:{resource_type}:{hour_key}"

            async def increment():
                # Increment counter
                await self.redis_client.incrby(redis_key, count)
                # Set expiry to 2 hours (allow for clock skew)
                await self.redis_client.expire(redis_key, 7200)

            try:
                asyncio.run(increment())
            except RuntimeError:
                # Already in async context
                loop = asyncio.get_event_loop()
                loop.run_until_complete(increment())

        except Exception as e:
            logger.error(f"Redis increment failed: {e}")

    def _increment_memory(self, user_id: str, resource_type: str, count: int):
        """Increment in memory"""
        self.usage_counts[user_id][resource_type] += count

        # Set reset time if not set
        if resource_type not in self.reset_times[user_id]:
            self.reset_times[user_id][resource_type] = datetime.utcnow()

# Global rate limiter instance
rate_limiter = RateLimiter()