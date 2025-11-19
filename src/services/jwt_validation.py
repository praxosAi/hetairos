"""
JWT Validation Service - Validates tokens via mypraxos-backend
"""
import os
import httpx
from typing import Optional, Dict, Any
from src.utils.logging import setup_logger
from urllib.parse import urljoin

logger = setup_logger(__name__)
BACKEND_URL = os.getenv('MYPRAXOS_BACKEND_URL')
# Cache for validation results (token -> payload)
# This reduces API calls for the same token
_validation_cache: Dict[str, Dict[str, Any]] = {}


class JWTValidationError(Exception):
    """Raised when JWT validation fails"""
    pass


async def validate_jwt_with_backend(token: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Validate JWT token using mypraxos-backend /auth/validate-token endpoint

    Args:
        token: JWT token string to validate
        use_cache: Whether to use cached validation results (default: True)

    Returns:
        User payload dict if valid, None if invalid

    Example return:
        {
            'user_id': '12345',
            'email': 'user@example.com',
            'name': 'John Doe',
            'role': 'user',
            'issued_at': 1234567890,
            'expires_at': 1234567890,
            'token_type': 'access'
        }
    """
    if not token:
        logger.warning("Empty token provided for validation")
        return None

    # Check cache first
    if use_cache and token in _validation_cache:
        logger.debug("Returning cached validation result")
        return _validation_cache[token]

    try:
        validation_url = urljoin(BACKEND_URL, "api/auth/validate-token")

        logger.debug(f"Validating token with backend: {validation_url}")

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                validation_url,
                json={"token": token},
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Service": "hetairos"
                }
            )

            if response.status_code == 200:
                data = response.json()

                if 'data' not in data:
                    logger.warning("Validation response missing 'data' field")
                    return None
                
                data = data['data']

                user_payload = data.get('user')

                if user_payload:
                    logger.info(f"Token validated successfully for user: {user_payload.get('user_id')}")

                    # Cache the result
                    if use_cache:
                        _validation_cache[token] = user_payload

                    return user_payload
                else:
                    logger.warning("Validation response missing user data")
                    return None

            elif response.status_code == 401:
                logger.warning("Token validation failed: Unauthorized (token expired or invalid)")
                return None

            else:
                logger.error(f"Token validation failed with status {response.status_code}: {response.text}")
                return None

    except httpx.TimeoutException:
        logger.error("Token validation timed out - backend unavailable")
        return None

    except httpx.RequestError as e:
        logger.error(f"Network error during token validation: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}", exc_info=True)
        return None


def clear_validation_cache():
    """Clear the validation cache (useful for testing or manual cache invalidation)"""
    global _validation_cache
    _validation_cache.clear()
    logger.debug("Validation cache cleared")


def extract_user_id(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Extract user_id from validation payload

    Args:
        payload: User payload from validation

    Returns:
        User ID string or None
    """
    if not payload:
        return None
    return payload.get('user_id')
