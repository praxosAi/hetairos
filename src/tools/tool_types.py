from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from enum import Enum


class ErrorCategory(str, Enum):
    """Categories of errors for better AI understanding"""
    # Authentication & Authorization
    AUTH_REQUIRED = "auth_required"           # No credentials/token found
    AUTH_EXPIRED = "auth_expired"             # Token expired, needs refresh
    AUTH_INVALID = "auth_invalid"             # Invalid credentials
    PERMISSION_DENIED = "permission_denied"   # Lacks permission for operation

    # Validation & Input
    INVALID_PARAMETER = "invalid_parameter"   # Wrong parameter format/value
    MISSING_PARAMETER = "missing_parameter"   # Required parameter missing
    PARAMETER_OUT_OF_RANGE = "parameter_out_of_range"  # Value outside valid range

    # Resource Issues
    NOT_FOUND = "not_found"                   # Resource doesn't exist
    ALREADY_EXISTS = "already_exists"         # Resource already exists
    RESOURCE_EXHAUSTED = "resource_exhausted" # Quota/limit reached

    # Network & Connectivity
    NETWORK_ERROR = "network_error"           # Connection/timeout issues
    SERVICE_UNAVAILABLE = "service_unavailable"  # Third-party service down
    RATE_LIMIT = "rate_limit"                 # Rate limit hit

    # Data & State
    INVALID_STATE = "invalid_state"           # Operation invalid in current state
    DATA_CONFLICT = "data_conflict"           # Concurrent modification conflict
    DATA_CORRUPTION = "data_corruption"       # Data integrity issue

    # System Issues
    INTERNAL_ERROR = "internal_error"         # Our system error
    UNKNOWN_ERROR = "unknown_error"           # Uncategorized error


class ErrorSeverity(str, Enum):
    """How severe is the error"""
    LOW = "low"           # Minor issue, operation partially succeeded
    MEDIUM = "medium"     # Operation failed but recoverable
    HIGH = "high"         # Critical failure, may affect other operations
    CRITICAL = "critical" # System-level failure


class RecoveryAction(BaseModel):
    """Structured recovery suggestion for the AI"""
    action_type: str  # e.g., "retry", "use_different_tool", "ask_user", "skip"
    description: str  # Human-readable explanation
    parameters: Optional[Dict[str, Any]] = None  # Parameters for the action
    estimated_delay: Optional[int] = None  # Seconds to wait before retry


class ErrorDetails(BaseModel):
    """Comprehensive error information"""
    category: ErrorCategory
    severity: ErrorSeverity

    # What went wrong
    error_message: str  # User-friendly message for AI
    technical_details: Optional[str] = None  # Technical error details
    original_exception: Optional[str] = None  # str(e) from exception

    # Context
    operation: str  # What was being attempted (e.g., "create_calendar_event")
    parameters: Optional[Dict[str, Any]] = None  # Sanitized params (no secrets)
    resource_id: Optional[str] = None  # ID of resource involved

    # Recovery guidance
    is_retryable: bool = False
    retry_after_seconds: Optional[int] = None
    recovery_actions: List[RecoveryAction] = Field(default_factory=list)

    # Additional context
    related_errors: Optional[List[str]] = None  # Related error messages
    documentation_link: Optional[str] = None  # Link to docs for this error
    affected_integrations: Optional[List[str]] = None  # Which integrations failed


class ToolExecutionResponse(BaseModel):
    """Enhanced tool execution response with rich error information"""
    status: str  # "success", "error", "partial_success", "need_user_input"

    # Success data
    result: Optional[Any] = None

    # Simple messages (for backwards compatibility)
    user_message: Optional[str] = None

    # Enhanced error information
    error_details: Optional[ErrorDetails] = None

    # Partial success tracking
    partial_results: Optional[Dict[str, Any]] = None
    failed_operations: Optional[List[str]] = None

    # Private field for backwards compatibility
    _system_error: Optional[str] = None

    @property
    def system_error(self) -> Optional[str]:
        """Backwards compatible system_error property"""
        if self.error_details:
            return self.error_details.technical_details or self.error_details.error_message
        return self._system_error

    @system_error.setter
    def system_error(self, value: str):
        """Allow legacy assignment"""
        self._system_error = value

    class Config:
        arbitrary_types_allowed = True
