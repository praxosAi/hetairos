from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass
class UserContext:
    """Holds all necessary information for the agent to operate on behalf of a user."""
    user_id: str
    user_record: Dict[str, Any]
    authenticated_clients: Dict[str, Any] = field(default_factory=dict)
    available_integrations: List[str] = field(default_factory=list)

async def create_user_context(user_id: str) -> UserContext:
    """
    Factory function to create a fully populated UserContext.
    This is a critical step that gathers all necessary user data, credentials,
    and authenticated API clients before an agent execution begins.
    """
    from src.services.user_service import user_service
    from src.services.integration_service import integration_service
    user_record = user_service.get_user_by_id(user_id) # Assuming phone number is the user_id for now
    if not user_record:
        return None

    # Get all authenticated clients (e.g., Google Calendar service, Gmail service)
    auth_clients = await integration_service.get_authenticated_clients(user_id)
    
    # Get the names of the available integrations
    avail_integrations = list(auth_clients.keys())
    
    return UserContext(
        user_id=user_id,
        user_record=user_record,
        authenticated_clients=auth_clients,
        available_integrations=avail_integrations
    )
