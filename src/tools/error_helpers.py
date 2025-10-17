"""
Error response builders for creating rich, actionable error responses.
These helpers provide the AI with detailed context and recovery guidance.
"""

from typing import Any, Dict, Optional, List
from src.tools.tool_types import (
    ToolExecutionResponse,
    ErrorDetails,
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction
)


class ErrorResponseBuilder:
    """Helper to build rich error responses with recovery guidance"""

    @staticmethod
    def auth_expired(
        operation: str,
        integration: str,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build auth expired error with recovery actions"""
        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.AUTH_EXPIRED,
                severity=ErrorSeverity.HIGH,
                error_message=f"Your {integration} authentication has expired. Please reconnect your account.",
                operation=operation,
                technical_details=technical_details,
                is_retryable=False,
                recovery_actions=[
                    RecoveryAction(
                        action_type="ask_user",
                        description=f"Inform the user that their {integration} connection has expired and guide them to reconnect",
                        parameters={"integration": integration, "action": "reconnect"}
                    )
                ],
                affected_integrations=[integration],
                **kwargs
            )
        )

    @staticmethod
    def auth_invalid(
        operation: str,
        integration: Optional[str] = None,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build invalid authentication error"""
        integration_msg = f" for {integration}" if integration else ""
        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.AUTH_INVALID,
                severity=ErrorSeverity.HIGH,
                error_message=f"Invalid authentication credentials{integration_msg}. Please verify your account connection.",
                operation=operation,
                technical_details=technical_details,
                is_retryable=False,
                recovery_actions=[
                    RecoveryAction(
                        action_type="ask_user",
                        description=f"Ask the user to reconnect{integration_msg} with valid credentials",
                        parameters={"integration": integration} if integration else None
                    )
                ],
                affected_integrations=[integration] if integration else None,
                **kwargs
            )
        )

    @staticmethod
    def permission_denied(
        operation: str,
        resource: Optional[str] = None,
        required_permission: Optional[str] = None,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build permission denied error"""
        resource_msg = f" to access {resource}" if resource else ""
        perm_msg = f" The required permission is: {required_permission}." if required_permission else ""
        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.PERMISSION_DENIED,
                severity=ErrorSeverity.HIGH,
                error_message=f"Permission denied{resource_msg}.{perm_msg}",
                operation=operation,
                technical_details=technical_details,
                resource_id=resource,
                is_retryable=False,
                recovery_actions=[
                    RecoveryAction(
                        action_type="ask_user",
                        description=f"Inform the user they need additional permissions{resource_msg}",
                        parameters={"required_permission": required_permission} if required_permission else None
                    ),
                    RecoveryAction(
                        action_type="use_alternative",
                        description="Try an alternative approach that doesn't require this permission"
                    )
                ],
                **kwargs
            )
        )

    @staticmethod
    def not_found(
        operation: str,
        resource_type: str,
        resource_id: str,
        suggestions: Optional[List[str]] = None,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build not found error"""
        recovery_actions = [
            RecoveryAction(
                action_type="verify_resource",
                description=f"Verify the {resource_type} identifier '{resource_id}' is correct",
                parameters={"resource_type": resource_type, "resource_id": resource_id}
            ),
            RecoveryAction(
                action_type="list_resources",
                description=f"List available {resource_type}s to find the correct one",
            )
        ]

        if suggestions:
            recovery_actions.append(
                RecoveryAction(
                    action_type="try_alternatives",
                    description=f"Try these similar {resource_type}s instead",
                    parameters={"suggestions": suggestions}
                )
            )

        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.NOT_FOUND,
                severity=ErrorSeverity.MEDIUM,
                error_message=f"The {resource_type} '{resource_id}' was not found.",
                operation=operation,
                technical_details=technical_details,
                resource_id=resource_id,
                is_retryable=False,
                recovery_actions=recovery_actions,
                **kwargs
            )
        )

    @staticmethod
    def rate_limit(
        operation: str,
        retry_after: int = 60,
        integration: Optional[str] = None,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build rate limit error"""
        integration_msg = f" for {integration}" if integration else ""
        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.RATE_LIMIT,
                severity=ErrorSeverity.MEDIUM,
                error_message=f"Rate limit exceeded{integration_msg}. Please wait {retry_after} seconds before retrying.",
                operation=operation,
                technical_details=technical_details,
                is_retryable=True,
                retry_after_seconds=retry_after,
                recovery_actions=[
                    RecoveryAction(
                        action_type="retry_with_delay",
                        description=f"Retry automatically after {retry_after} seconds",
                        estimated_delay=retry_after
                    ),
                    RecoveryAction(
                        action_type="inform_user",
                        description=f"Inform user about rate limit and {retry_after}s delay",
                    )
                ],
                affected_integrations=[integration] if integration else None,
                **kwargs
            )
        )

    @staticmethod
    def invalid_parameter(
        operation: str,
        param_name: str,
        param_value: Any,
        expected_format: str,
        validation_error: Optional[str] = None,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build invalid parameter error"""
        error_msg = f"Parameter '{param_name}' has invalid value. Expected format: {expected_format}"
        if validation_error:
            error_msg += f". Validation error: {validation_error}"

        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.INVALID_PARAMETER,
                severity=ErrorSeverity.LOW,
                error_message=error_msg,
                operation=operation,
                technical_details=technical_details,
                parameters={param_name: str(param_value)},
                is_retryable=True,
                recovery_actions=[
                    RecoveryAction(
                        action_type="fix_parameter",
                        description=f"Correct the '{param_name}' parameter to match format: {expected_format}",
                        parameters={
                            "param_name": param_name,
                            "expected_format": expected_format,
                            "current_value": str(param_value)
                        }
                    ),
                    RecoveryAction(
                        action_type="ask_user",
                        description=f"Ask the user to provide a valid {param_name}",
                    )
                ],
                **kwargs
            )
        )

    @staticmethod
    def missing_parameter(
        operation: str,
        param_name: str,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build missing parameter error"""
        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.MISSING_PARAMETER,
                severity=ErrorSeverity.MEDIUM,
                error_message=f"Required parameter '{param_name}' is missing.",
                operation=operation,
                technical_details=technical_details,
                is_retryable=True,
                recovery_actions=[
                    RecoveryAction(
                        action_type="ask_user",
                        description=f"Ask the user to provide the missing '{param_name}' parameter",
                        parameters={"param_name": param_name}
                    )
                ],
                **kwargs
            )
        )

    @staticmethod
    def network_error(
        operation: str,
        integration: Optional[str] = None,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build network error"""
        integration_msg = f" with {integration}" if integration else ""
        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.NETWORK_ERROR,
                severity=ErrorSeverity.MEDIUM,
                error_message=f"Network error occurred while communicating{integration_msg}. This may be a temporary issue.",
                operation=operation,
                technical_details=technical_details,
                is_retryable=True,
                retry_after_seconds=5,
                recovery_actions=[
                    RecoveryAction(
                        action_type="retry",
                        description="Retry the operation (network issues are often temporary)",
                        estimated_delay=5
                    ),
                    RecoveryAction(
                        action_type="inform_user",
                        description="If retries fail, inform the user about connectivity issues",
                    )
                ],
                affected_integrations=[integration] if integration else None,
                **kwargs
            )
        )

    @staticmethod
    def service_unavailable(
        operation: str,
        service: str,
        technical_details: Optional[str] = None,
        **kwargs
    ) -> ToolExecutionResponse:
        """Build service unavailable error"""
        return ToolExecutionResponse(
            status="error",
            error_details=ErrorDetails(
                category=ErrorCategory.SERVICE_UNAVAILABLE,
                severity=ErrorSeverity.HIGH,
                error_message=f"The {service} service is currently unavailable. This may be a temporary outage.",
                operation=operation,
                technical_details=technical_details,
                is_retryable=True,
                retry_after_seconds=30,
                recovery_actions=[
                    RecoveryAction(
                        action_type="retry_later",
                        description=f"Retry after {service} service is back online",
                        estimated_delay=30
                    ),
                    RecoveryAction(
                        action_type="inform_user",
                        description=f"Inform user that {service} is temporarily unavailable",
                    ),
                    RecoveryAction(
                        action_type="use_alternative",
                        description=f"If available, use an alternative to {service}",
                    )
                ],
                affected_integrations=[service],
                **kwargs
            )
        )

    @staticmethod
    def from_exception(
        operation: str,
        exception: Exception,
        integration: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ToolExecutionResponse:
        """
        Smart error categorization from exception.
        Analyzes the exception and creates an appropriate rich error response.
        """
        error_str = str(exception)
        error_lower = error_str.lower()
        exception_type = type(exception).__name__

        # Pattern matching for common errors
        if "401" in error_str or "unauthorized" in error_lower:
            if "expired" in error_lower or "token" in error_lower:
                return ErrorResponseBuilder.auth_expired(
                    operation=operation,
                    integration=integration or "service",
                    technical_details=f"{exception_type}: {error_str}",
                    original_exception=error_str
                )
            return ErrorResponseBuilder.auth_invalid(
                operation=operation,
                integration=integration,
                technical_details=f"{exception_type}: {error_str}",
                original_exception=error_str
            )

        elif "403" in error_str or "forbidden" in error_lower or "permission" in error_lower:
            return ErrorResponseBuilder.permission_denied(
                operation=operation,
                technical_details=f"{exception_type}: {error_str}",
                original_exception=error_str
            )

        elif "404" in error_str or "not found" in error_lower:
            # Try to extract resource info from context
            resource_type = context.get("resource_type", "resource") if context else "resource"
            resource_id = context.get("resource_id", "unknown") if context else "unknown"
            return ErrorResponseBuilder.not_found(
                operation=operation,
                resource_type=resource_type,
                resource_id=resource_id,
                technical_details=f"{exception_type}: {error_str}",
                original_exception=error_str
            )

        elif "429" in error_str or "rate limit" in error_lower or "too many requests" in error_lower:
            # Try to extract retry-after from error
            retry_after = 60  # default
            if "retry after" in error_lower:
                try:
                    # Try to parse retry-after value
                    import re
                    match = re.search(r'retry.*?(\d+)', error_lower)
                    if match:
                        retry_after = int(match.group(1))
                except:
                    pass
            return ErrorResponseBuilder.rate_limit(
                operation=operation,
                retry_after=retry_after,
                integration=integration,
                technical_details=f"{exception_type}: {error_str}",
                original_exception=error_str
            )

        elif "timeout" in error_lower or "connection" in error_lower or "network" in error_lower:
            return ErrorResponseBuilder.network_error(
                operation=operation,
                integration=integration,
                technical_details=f"{exception_type}: {error_str}",
                original_exception=error_str
            )

        elif "503" in error_str or "service unavailable" in error_lower or "temporarily unavailable" in error_lower:
            return ErrorResponseBuilder.service_unavailable(
                operation=operation,
                service=integration or "external service",
                technical_details=f"{exception_type}: {error_str}",
                original_exception=error_str
            )

        else:
            # Generic error - still provide structure
            return ToolExecutionResponse(
                status="error",
                error_details=ErrorDetails(
                    category=ErrorCategory.UNKNOWN_ERROR,
                    severity=ErrorSeverity.MEDIUM,
                    error_message=f"An unexpected error occurred during {operation}: {error_str}",
                    operation=operation,
                    technical_details=f"{exception_type}: {error_str}",
                    original_exception=error_str,
                    is_retryable=True,  # Safe default
                    retry_after_seconds=5,
                    recovery_actions=[
                        RecoveryAction(
                            action_type="retry",
                            description="Retry the operation in case this was a transient error",
                            estimated_delay=5
                        ),
                        RecoveryAction(
                            action_type="report_error",
                            description="If the error persists, report it to the development team",
                        )
                    ],
                    affected_integrations=[integration] if integration else None
                )
            )
