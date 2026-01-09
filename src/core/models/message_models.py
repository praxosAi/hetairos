"""
Message categorization models for conversation and execution log separation.

This module provides enums and utilities for categorizing messages to distinguish
between user-facing conversation messages and internal execution/system logs.
"""

from enum import Enum


class MessageCategory(str, Enum):
    """
    Categorizes messages to separate user-facing conversation from execution logs.

    This enum is critical for UI/UX - it allows the frontend to display only
    relevant conversation messages while hiding internal execution details.
    """

    CONVERSATION = "conversation"
    """
    User-facing conversation messages between user and assistant.

    Includes:
    - User text messages
    - Assistant responses to user
    - Media messages (images, videos, files) sent by user or assistant
    - Message captions

    These are the messages that should be displayed in the conversation UI.
    """

    TOOL_EXECUTION = "tool_execution"
    """
    Internal tool execution logs.

    Includes:
    - Tool call initiations (e.g., "[Calling tools: gmail_search]")
    - Tool execution results (raw API responses, JSON outputs)
    - Async task status updates (requested, success, failed)

    These are internal execution details that should be hidden from the user
    but preserved for debugging and agent context.
    """

    SCHEDULED_OUTPUT = "scheduled_output"
    """
    Outputs from scheduled, recurring, or triggered tasks.

    Includes:
    - Results from scheduled tasks (source="scheduled")
    - Outputs from recurring tasks (source="recurring")
    - Triggered action results (source="triggered")

    These may or may not be shown to users depending on the task configuration,
    but should be separate from organic conversation flow.
    """

    SYSTEM_INTERNAL = "system_internal"
    """
    System-level internal messages.

    Includes:
    - System notes and diagnostics
    - Internal state messages
    - Debug information

    These are purely internal and should never be shown to users.
    Currently rarely used, reserved for future internal messaging needs.
    """


# Default category for backward compatibility with existing messages
DEFAULT_MESSAGE_CATEGORY = MessageCategory.CONVERSATION


def get_category_from_metadata(metadata: dict) -> MessageCategory:
    """
    Determine message category from metadata patterns (for legacy messages).

    This function provides backward compatibility by inferring the category
    from existing metadata patterns in messages created before the category
    field was added.

    Args:
        metadata: Message metadata dictionary

    Returns:
        MessageCategory: The inferred category

    Examples:
        >>> get_category_from_metadata({"message_type": "tool_result"})
        MessageCategory.TOOL_EXECUTION

        >>> get_category_from_metadata({"source": "scheduled"})
        MessageCategory.SCHEDULED_OUTPUT

        >>> get_category_from_metadata({"forwarded": True})
        MessageCategory.CONVERSATION
    """
    # Tool execution indicators
    if metadata.get("message_type") == "tool_result":
        return MessageCategory.TOOL_EXECUTION

    if "tool_calls" in metadata or "tool_call_id" in metadata:
        return MessageCategory.TOOL_EXECUTION

    if "asynchronous_task_status" in metadata:
        return MessageCategory.TOOL_EXECUTION

    # Scheduled/triggered task indicators
    if metadata.get("source") in ["scheduled", "recurring", "triggered"]:
        return MessageCategory.SCHEDULED_OUTPUT

    # Default to conversation
    return MessageCategory.CONVERSATION
