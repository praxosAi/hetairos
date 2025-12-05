"""
OAuth Scope Validator

Validates that OAuth tokens have required scopes before making API calls.
Provides better error messages and enables incremental authorization.
"""

from typing import List, Optional, Set
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)


class InsufficientScopeError(Exception):
    """
    Raised when an OAuth token is missing required scopes for an operation.

    This is a user-facing error that should result in clear messaging about
    needing to reconnect the integration with additional permissions.
    """

    def __init__(self, missing_scopes: List[str], operation: str, integration: str = None):
        self.missing_scopes = missing_scopes
        self.operation = operation
        self.integration = integration

        integration_name = f" ({integration})" if integration else ""
        message = (
            f"Missing required permissions for '{operation}'{integration_name}. "
            f"Required scopes: {', '.join(missing_scopes)}. "
            f"Please reconnect your account with the necessary permissions."
        )
        super().__init__(message)


class ScopeValidator:
    """
    Validates OAuth token has required scopes for operations.

    Usage:
        validator = ScopeValidator(token_scopes)
        validator.require_scopes(['gmail.modify'], 'archive_email')
    """

    def __init__(self, token_scopes: List[str], integration_name: str = None):
        """
        Initialize with scopes from OAuth token.

        Args:
            token_scopes: List of scope URLs from token
            integration_name: Name of integration (for error messages)
        """
        self.token_scopes: Set[str] = set(token_scopes or [])
        self.integration_name = integration_name

        logger.debug(
            f"ScopeValidator initialized for {integration_name or 'unknown'} "
            f"with {len(self.token_scopes)} scopes"
        )

    def require_scopes(
        self,
        required_scopes: List[str],
        operation: str,
        allow_alternatives: bool = False
    ) -> None:
        """
        Validate token has all required scopes.

        Args:
            required_scopes: List of required scope URLs
            operation: Name of operation (for error message)
            allow_alternatives: If True, having ANY of the required scopes is sufficient

        Raises:
            InsufficientScopeError: If required scopes are missing
        """
        if not required_scopes:
            logger.debug(f"No scope requirements for {operation}")
            return

        if allow_alternatives:
            # Need at least ONE of the required scopes
            if not self.has_any_scope(required_scopes):
                logger.warning(
                    f"Missing all alternative scopes for {operation}: {required_scopes}. "
                    f"Token has: {self.token_scopes}"
                )
                raise InsufficientScopeError(
                    required_scopes,
                    operation,
                    self.integration_name
                )
        else:
            # Need ALL required scopes
            missing_scopes = []
            for required_scope in required_scopes:
                if required_scope not in self.token_scopes:
                    missing_scopes.append(required_scope)

            if missing_scopes:
                logger.warning(
                    f"Missing scopes for {operation}: {missing_scopes}. "
                    f"Token has: {self.token_scopes}"
                )
                raise InsufficientScopeError(
                    missing_scopes,
                    operation,
                    self.integration_name
                )

        logger.debug(f"Scope validation passed for {operation}")

    def has_scope(self, scope: str) -> bool:
        """Check if token has a specific scope"""
        return scope in self.token_scopes

    def has_any_scope(self, scopes: List[str]) -> bool:
        """
        Check if token has at least one of the given scopes.

        Useful for operations that can work with multiple scope options
        (e.g., gmail.send OR gmail.modify both allow sending)
        """
        return any(scope in self.token_scopes for scope in scopes)

    def has_all_scopes(self, scopes: List[str]) -> bool:
        """Check if token has all of the given scopes"""
        return all(scope in self.token_scopes for scope in scopes)

    def get_missing_scopes(self, required_scopes: List[str]) -> List[str]:
        """
        Get list of missing scopes.

        Args:
            required_scopes: List of required scope URLs

        Returns:
            List of missing scopes (empty if all present)
        """
        return [
            scope for scope in required_scopes
            if scope not in self.token_scopes
        ]

    def log_scope_status(self) -> None:
        """Log current scopes for debugging"""
        logger.info(
            f"Token scopes for {self.integration_name or 'unknown'}: "
            f"{', '.join(sorted(self.token_scopes))}"
        )
