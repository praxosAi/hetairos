from datetime import datetime, timedelta
from typing import Dict, DefaultDict
from collections import defaultdict
from src.config.settings import settings

class RateLimiter:
    def __init__(self):
        self.usage_counts = defaultdict(lambda: defaultdict(int))
        self.reset_times = defaultdict(lambda: defaultdict(lambda: datetime.utcnow()))
    
    def check_limit(self, user_id: str, resource_type: str) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit for resource type.
        Returns (is_allowed, remaining_count)
        """
        limits = {
            "emails": settings.MAX_EMAILS,
            "email_attachments": settings.MAX_EMAIL_ATTACHMENTS,
            "whatsapp_messages": settings.MAX_WHATSAPP_MESSAGES,
            "telegram_messages": settings.MAX_WHATSAPP_MESSAGES,  # Same limit as WhatsApp
            "gmail_webhooks": settings.MAX_GMAIL_WEBHOOKS_PER_HOUR,
            "gmail_history_calls": settings.MAX_HISTORY_CALLS_PER_HOUR,
        }
        
        if resource_type not in limits:
            return True, float('inf')
        
        max_limit = limits[resource_type]
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
        self.usage_counts[user_id][resource_type] += count
        
        # Set reset time if not set
        if resource_type not in self.reset_times[user_id]:
            self.reset_times[user_id][resource_type] = datetime.utcnow()

# Global rate limiter instance
rate_limiter = RateLimiter()