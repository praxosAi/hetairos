from typing import List, Set
import logging

logger = logging.getLogger(__name__)

# Map service names to their provider
SERVICE_TO_PROVIDER = {
    'gmail': 'google',
    'google_calendar': 'google',
    'google_drive': 'google',
    'outlook': 'microsoft',
    'outlook_calendar': 'microsoft',
    'onedrive': 'microsoft',
}

# Map providers to possible services
PROVIDER_TO_SERVICES = {
    'google': ['gmail', 'google_calendar', 'google_drive'],
    'microsoft': ['outlook', 'outlook_calendar', 'onedrive'],
}

# Define scope requirements for each service
SERVICE_SCOPE_REQUIREMENTS = {
    'gmail': [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/contacts.readonly",
        "https://www.googleapis.com/auth/contacts.other.readonly"
    ],
    'google_calendar': [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly"
    ],
    'google_drive': [
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/documents',
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/presentations',
    ],
    'outlook': [
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/Mail.ReadWrite"
    ],
    'outlook_calendar': [
        "https://graph.microsoft.com/Calendars.Read",
        "https://graph.microsoft.com/Calendars.ReadWrite"
    ],
    'onedrive': [
         "https://graph.microsoft.com/Files.Read",
        "https://graph.microsoft.com/Files.ReadWrite",
        "https://graph.microsoft.com/Files.Read.All"
    ]
}

def normalize_to_provider(name: str) -> str:
    """
    Convert service name to provider name.

    Examples:
        'gmail' → 'google'
        'google_calendar' → 'google'
        'outlook' → 'microsoft'
        'notion' → 'notion' (unchanged)
    """
    return SERVICE_TO_PROVIDER.get(name, name)

def check_service_scopes(service_name: str, granted_scopes: List[str]) -> bool:
    """Check if granted scopes satisfy service requirements."""
    if service_name not in SERVICE_SCOPE_REQUIREMENTS:
        # If no requirements defined, assume available
        return True

    requirements = SERVICE_SCOPE_REQUIREMENTS[service_name]
    granted_set = set(granted_scopes)

    return all(scope in granted_set for scope in requirements)

def get_available_services(provider: str, granted_scopes: List[str]) -> Set[str]:
    """Return services available given provider and scopes."""
    if provider not in PROVIDER_TO_SERVICES:
        return set()

    available = set()
    for service in PROVIDER_TO_SERVICES[provider]:
        if check_service_scopes(service, granted_scopes):
            available.add(service)
        else:
            logger.debug(f"Service '{service}' not available - insufficient scopes")

    return available
