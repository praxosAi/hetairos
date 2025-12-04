"""
Centralized Tier Limits Configuration

This file defines the feature limits for each subscription tier.
To modify tier limits, update the values in this file only.
"""

from enum import Enum
from typing import Dict, Any, Optional


class SubscriptionTier(str, Enum):
    """Subscription tier levels"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TierLimits:
    """Centralized tier limits configuration"""

    # Tier definitions
    TIERS = {
        SubscriptionTier.FREE: {
            # Messaging Platform Limits (only ONE total)
            "messaging_platforms_total": 1,  # Can only connect ONE of: Telegram, WhatsApp, or iMessage
            "messaging_platforms_allowed": ["telegram", "whatsapp", "imessage"],

            # Email Workspace Limits (only ONE total)
            "email_workspaces_total": 1,  # Can only connect ONE of: Gmail or Outlook
            "email_workspaces_allowed": ["gmail", "outlook"],

            # Feature Restrictions
            "video_generation_enabled": False,  # No video generation for free tier

            # Additional Integration Limits
            "calendar_integrations_total": 1,  # One calendar (Google or Microsoft)
            "file_storage_total": 0,  # No additional file storage integrations (Dropbox, etc.)
            "project_management_total": 0,  # No project management (Notion, Trello, etc.)
            "communication_tools_total": 0,  # No additional communication tools (Slack, Discord, etc.)

            # Usage Limits (for future rate limiting)
            "messages_per_day": 50,
            "messages_per_month": 1000,
            "api_calls_per_hour": 100,
            "file_uploads_per_day": 10,
            "max_file_size_mb": 10,
        },

        SubscriptionTier.PRO: {
            # Messaging Platform Limits (unlimited)
            "messaging_platforms_total": -1,  # -1 = unlimited
            "messaging_platforms_allowed": ["telegram", "whatsapp", "imessage"],

            # Email Workspace Limits (unlimited)
            "email_workspaces_total": -1,  # Unlimited
            "email_workspaces_allowed": ["gmail", "outlook"],

            # Feature Restrictions
            "video_generation_enabled": True,  # Video generation enabled

            # Additional Integration Limits
            "calendar_integrations_total": -1,  # Unlimited
            "file_storage_total": -1,  # Unlimited file storage integrations
            "project_management_total": -1,  # Unlimited project management tools
            "communication_tools_total": -1,  # Unlimited communication tools

            # Usage Limits
            "messages_per_day": -1,  # Unlimited
            "messages_per_month": -1,  # Unlimited
            "api_calls_per_hour": 1000,
            "file_uploads_per_day": -1,  # Unlimited
            "max_file_size_mb": 100,
        },

        SubscriptionTier.ENTERPRISE: {
            # Same as PRO for now, can customize later
            "messaging_platforms_total": -1,
            "messaging_platforms_allowed": ["telegram", "whatsapp", "imessage"],
            "email_workspaces_total": -1,
            "email_workspaces_allowed": ["gmail", "outlook"],
            "video_generation_enabled": True,
            "calendar_integrations_total": -1,
            "file_storage_total": -1,
            "project_management_total": -1,
            "communication_tools_total": -1,
            "messages_per_day": -1,
            "messages_per_month": -1,
            "api_calls_per_hour": 5000,
            "file_uploads_per_day": -1,
            "max_file_size_mb": 500,
        }
    }

    # Integration type mappings
    INTEGRATION_CATEGORIES = {
        "messaging": ["telegram", "whatsapp", "imessage"],
        "email": ["gmail", "outlook"],
        "calendar": ["google_calendar", "microsoft_calendar"],
        "file_storage": ["dropbox", "google_drive", "onedrive"],
        "project_management": ["notion", "trello", "asana"],
        "communication": ["slack", "discord", "teams"]
    }

    @classmethod
    def get_limits(cls, tier: str) -> Dict[str, Any]:
        """
        Get the limits for a specific tier.

        Args:
            tier: The subscription tier (free, pro, enterprise)

        Returns:
            Dictionary containing all limits for the tier
        """
        tier_enum = SubscriptionTier(tier.lower())
        return cls.TIERS.get(tier_enum, cls.TIERS[SubscriptionTier.FREE])

    @classmethod
    def get_limit(cls, tier: str, limit_name: str) -> Any:
        """
        Get a specific limit value for a tier.

        Args:
            tier: The subscription tier
            limit_name: The name of the limit to retrieve

        Returns:
            The limit value, or None if not found
        """
        limits = cls.get_limits(tier)
        return limits.get(limit_name)

    @classmethod
    def is_feature_enabled(cls, tier: str, feature_name: str) -> bool:
        """
        Check if a feature is enabled for a tier.

        Args:
            tier: The subscription tier
            feature_name: The feature to check (e.g., 'video_generation_enabled')

        Returns:
            True if the feature is enabled, False otherwise
        """
        limits = cls.get_limits(tier)
        return limits.get(feature_name, False)

    @classmethod
    def is_unlimited(cls, limit_value: int) -> bool:
        """Check if a limit value represents unlimited access"""
        return limit_value == -1

    @classmethod
    def check_integration_limit(cls, tier: str, integration_type: str, current_count: int) -> tuple[bool, Optional[str]]:
        """
        Check if user can add another integration of a specific type.

        Args:
            tier: The subscription tier
            integration_type: The type of integration (e.g., 'telegram', 'gmail')
            current_count: Current number of integrations of this category

        Returns:
            Tuple of (can_add: bool, error_message: Optional[str])
        """
        limits = cls.get_limits(tier)

        # Determine the category and limit
        category = None
        limit_key = None

        for cat, types in cls.INTEGRATION_CATEGORIES.items():
            if integration_type.lower() in types:
                category = cat
                if category == "messaging":
                    limit_key = "messaging_platforms_total"
                elif category == "email":
                    limit_key = "email_workspaces_total"
                elif category == "calendar":
                    limit_key = "calendar_integrations_total"
                elif category == "file_storage":
                    limit_key = "file_storage_total"
                elif category == "project_management":
                    limit_key = "project_management_total"
                elif category == "communication":
                    limit_key = "communication_tools_total"
                break

        if not limit_key:
            # Unknown integration type, allow by default
            return True, None

        max_allowed = limits.get(limit_key, 0)

        # Check if unlimited
        if cls.is_unlimited(max_allowed):
            return True, None

        # Check if limit reached
        if current_count >= max_allowed:
            if tier == SubscriptionTier.FREE:
                return False, f"Free tier is limited to {max_allowed} {category} integration(s). Upgrade to Pro for unlimited access."
            else:
                return False, f"Maximum {category} integrations reached for your tier."

        return True, None

    @classmethod
    def get_category_count(cls, integrations: list, category: str) -> int:
        """
        Count how many integrations belong to a specific category.

        Args:
            integrations: List of integration objects with 'type' or 'provider' field
            category: The category to count (messaging, email, etc.)

        Returns:
            Count of integrations in that category
        """
        category_types = cls.INTEGRATION_CATEGORIES.get(category, [])
        count = 0

        for integration in integrations:
            integration_type = integration.get('type') or integration.get('provider', '').lower()
            if integration_type.lower() in category_types:
                count += 1

        return count

    @classmethod
    def get_tier_description(cls, tier: str) -> Dict[str, Any]:
        """
        Get a human-readable description of tier limits.

        Args:
            tier: The subscription tier

        Returns:
            Dictionary with formatted descriptions
        """
        limits = cls.get_limits(tier)

        def format_limit(value: int) -> str:
            return "Unlimited" if cls.is_unlimited(value) else str(value)

        return {
            "tier": tier,
            "messaging_platforms": format_limit(limits["messaging_platforms_total"]),
            "email_workspaces": format_limit(limits["email_workspaces_total"]),
            "video_generation": "Enabled" if limits["video_generation_enabled"] else "Disabled",
            "messages_per_month": format_limit(limits["messages_per_month"]),
            "max_file_size_mb": f"{limits['max_file_size_mb']} MB",
        }


# Export for easy access
FREE_TIER_LIMITS = TierLimits.TIERS[SubscriptionTier.FREE]
PRO_TIER_LIMITS = TierLimits.TIERS[SubscriptionTier.PRO]
ENTERPRISE_TIER_LIMITS = TierLimits.TIERS[SubscriptionTier.ENTERPRISE]
