import secrets
import logging
from typing import Dict, Optional
from langchain_core.tools import Tool

from src.utils.redis_client import redis_client
from src.config.settings import settings

logger = logging.getLogger(__name__)

# This mapping helps construct the correct URL for the provider.
# It translates a specific integration name (like 'gmail') to the provider name ('google').
INTEGRATION_NAME_TO_PROVIDER_MAP = {
    # Google
    "gmail": "google",
    "google_calendar": "google",
    "google_drive": "google",
    # Microsoft
    "outlook": "microsoft",
    "onedrive": "microsoft",
    "microsoft_calendar": "microsoft",
    # Other
    "notion": "notion",
    "dropbox": "dropbox",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "imessage": "imessage",
}

def get_oauth_initiation_url(integration_name: str, user_id: str) -> Optional[Dict[str, str]]:
    """
    Generates a secure, single-use URL for a user to initiate an OAuth2 flow
    for a specific integration. This is designed for messaging platforms where
    a standard web login flow is not possible.

    Args:
        integration_name: The name of the integration to connect (e.g., 'gmail', 'notion').
        user_id: The unique identifier for the user initiating the request.

    Returns:
        A dictionary containing the 'oauth_url' if successful, otherwise None.
    """
    provider = INTEGRATION_NAME_TO_PROVIDER_MAP.get(integration_name)
    if not provider:
        logger.error(f"Invalid or unsupported integration_name: {integration_name}")
        return None

    try:
        # Generate a secure, random token that is safe to include in a URL.
        login_token = secrets.token_urlsafe(32)
        
        # Store the token in Redis with the user's ID. Set a 5-minute expiry
        # to limit the time window for authentication.
        redis_client.set(f"login_token:{login_token}", user_id, ex=300)
        
        # Construct the full URL pointing to the backend's messaging OAuth endpoint.
        oauth_url = (
            f"{settings.PRAXOS_BASE_URL}/api/auth/initiate-messaging-oauth/{provider}?"
            f"integration_name={integration_name}&login_token={login_token}&redirect_url=https://app.mypraxos.com/integrations"
        )
        
        logger.info(f"Generated OAuth URL for user {user_id} and integration {integration_name}")
        
        return {"oauth_url": oauth_url}

    except Exception as e:
        logger.error(f"Failed to generate OAuth URL for user {user_id}: {e}", exc_info=True)
        return None

def create_integration_tools(user_id: str) -> list[Tool]:
    """Creates a list of tools for handling integrations."""
    tools = [
        Tool(
            name="get_oauth_initiation_url",
            description=(
                "Generates a secure, single-use URL for a user to connect a new integration. if the user wants to use a tool for an integration they haven't connected yet, or asks to integrate it, use this tool."
                "like Gmail, Outlook, Notion, etc. The user must be asked to click this link "
                "to complete the authentication. Provide the 'integration_name' as an argument."
            ),
            func=lambda integration_name: get_oauth_initiation_url(integration_name, user_id),
        )
    ]
    return tools