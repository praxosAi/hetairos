from datetime import datetime
from typing import List, Dict, Any
import pytz
from src.utils.logging import setup_logger
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.services.user_service import user_service  # uses the global instance you showed

# Optional: restrict to languages you plan to support (expand as needed)
SUPPORTED_LANGS = {"en", "es", "pt", "fr", "de", "it", "vi", "fa"}

def _utc_now_iso() -> str:
    return datetime.now(pytz.UTC).isoformat()

def _ensure_list_of_str(values: List[str]) -> List[str]:
    if not isinstance(values, list):
        raise ValueError("Expected a list of strings.")
    cleaned = []
    for v in values:
        if not isinstance(v, str):
            raise ValueError("All annotations must be strings.")
        s = v.strip()
        if s:
            cleaned.append(s)
    # De-duplicate preserving order
    seen = set()
    unique = []
    for s in cleaned:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique

def _validate_timezone(tz_name: str) -> str:
    tz = tz_name.strip()
    # pytz supports "US/Eastern", "America/New_York", etc.
    if tz not in pytz.all_timezones:
        raise ValueError(f"Invalid timezone: {tz}")
    return tz

def _validate_assistant_name(name: str) -> str:
    n = name.strip()
    if not n:
        raise ValueError("Assistant name cannot be empty.")
    if len(n) > 50:
        raise ValueError("Assistant name must be 50 characters or fewer.")
    return n

def _validate_language(lang_code: str) -> str:
    code = lang_code.strip().lower()
    if code not in SUPPORTED_LANGS:
        # If you prefer to allow anything, replace with a length check instead.
        raise ValueError(f"Unsupported language code: {code}. Allowed: {sorted(SUPPORTED_LANGS)}")
    return code

def create_preference_tools(user_id: str, tool_registry = None) -> list:
    """Create basic user preference tools bound to a specific user_id."""
    logger = setup_logger(f"preference_tools")
    @tool
    def add_user_preference_annotation(new_preference_text: List[str]) -> ToolExecutionResponse:
        """
        Add one or more preference annotations for the user.
        this is for when the user mentions a new preference in conversation, and we want to remember it for future interactions.
        - If the 'annotations' field doesn't exist, it will be created as a list[str].
        - If it exists, new items are merged (de-duplicated, order preserved).
        Args:
            new_preference_text: List of annotation strings to add.
        Returns:
            ToolExecutionResponse with success status and updated preferences
        """
        try:
            to_add = _ensure_list_of_str(new_preference_text)
            current = user_service.get_user_preferences(user_id) or {}
            existing = current.get("annotations", [])
            if not isinstance(existing, list):
                existing = []
            existing_clean = _ensure_list_of_str(existing)
            # Merge and de-dupe preserving order
            merged = existing_clean + [a for a in to_add if a not in set(existing_clean)]
            payload = {
                "annotations": merged,
                "updated_at": _utc_now_iso(),
            }
            ok = user_service.add_new_preference_annotations(user_id, payload,True)
            return ToolExecutionResponse(
                status="success",
                result={
                    "ok": bool(ok),
                    "message": "Annotations updated.",
                    "updated": {"annotations": merged, "updated_at": payload["updated_at"]},
                }
            )
        except Exception as e:
            logger.error(f"Failed to add annotations: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="add_user_preference_annotation",
                exception=e,
                integration="user_preferences"
            )

    @tool
    def set_assistant_name(assistant_name: str) -> ToolExecutionResponse:
        """
        Update the assistant's display name in user preferences.
        Args:
            assistant_name: The new assistant name (<= 50 chars).
        """
        try:
            name = _validate_assistant_name(assistant_name)
            payload = {
                "assistant_name": name,
                "updated_at": _utc_now_iso(),
                "user_id": user_id,
            }
            ok = user_service.add_new_preference_annotations(user_id, payload)
            return ToolExecutionResponse(
                status="success",
                result={
                    "ok": bool(ok),
                    "message": "Assistant name updated.",
                    "updated": {"assistant_name": name, "updated_at": payload["updated_at"]},
                }
            )
        except Exception as e:
            logger.error(f"Failed to update assistant name: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="set_assistant_name",
                exception=e,
                integration="user_preferences",
                context={"assistant_name": assistant_name}
            )

    @tool
    def set_timezone(timezone_name: str) -> ToolExecutionResponse:
        """
        Update the user's timezone (pytz name, e.g., 'US/Eastern' or 'America/New_York').
        Args:
            timezone_name: Valid pytz timezone string.
        """
        try:
            tz = _validate_timezone(timezone_name)
            payload = {
                "timezone": tz,
                "updated_at": _utc_now_iso(),
                "user_id": user_id,
            }
            ok = user_service.add_new_preference_annotations(user_id, payload)
            return ToolExecutionResponse(
                status="success",
                result={
                    "ok": bool(ok),
                    "message": "Timezone updated.",
                    "updated": {"timezone": tz, "updated_at": payload["updated_at"]},
                }
            )
        except Exception as e:
            logger.error(f"Failed to update timezone: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="set_timezone",
                exception=e,
                integration="user_preferences",
                context={"timezone_name": timezone_name}
            )

    @tool
    def set_language_response(language_code: str) -> ToolExecutionResponse:
        """
        Update the preferred response language.
        Args:
            language_code: Short language code (e.g., 'en', 'es', 'pt').
        """
        try:
            code = _validate_language(language_code)
            payload = {
                "language_responses": code,
                "updated_at": _utc_now_iso(),
                "user_id": user_id,
            }
            ok = user_service.add_new_preference_annotations(user_id, payload)
            
            return ToolExecutionResponse(
                status="success",
                result={
                    "ok": bool(ok),
                    "message": "Language preference updated.",
                    "updated": {"language_responses": code, "updated_at": payload["updated_at"]},
                }
            )
        except Exception as e:
            logger.error(f"Failed to update language: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="set_language_response",
                exception=e,
                integration="user_preferences",
                context={"language_code": language_code}
            )

    @tool
    def delete_user_preference_annotations(annotations_to_delete: List[str]) -> ToolExecutionResponse:
        """
        Delete one or more annotations from the user's preferences.
        Only 'annotations' are affected—no other fields can be deleted.
        Args:
            annotations_to_delete: List of exact annotation strings to remove.
        Returns:
            ToolExecutionResponse with success status and updated annotations
        """
        try:
            # Reuse your validator to ensure list[str] with trimming & de-dupe
            to_delete = _ensure_list_of_str(annotations_to_delete)
            if not to_delete:
                return ToolExecutionResponse(
                    status="success",
                    result={"ok": False, "message": "No annotations provided to delete."}
                )

            ok = user_service.remove_preference_annotations(user_id, to_delete)

            # Fetch the latest state to return an accurate view
            current = user_service.get_user_preferences(user_id) or {}
            updated_at = _utc_now_iso()  # reflect current call time in response (db has its own UTC too)
            annotations = current.get("annotations", [])
            if not isinstance(annotations, list):
                annotations = []

            return ToolExecutionResponse(
                status="success",
                result={
                    "ok": bool(ok),
                    "message": "Annotations deleted." if ok else "No matching annotations found.",
                    "updated": {"annotations": annotations, "updated_at": updated_at},
                }
            )
        except Exception as e:
            logger.error(f"Failed to delete annotations: {str(e)}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="delete_user_preference_annotations",
                exception=e,
                integration="user_preferences"
            )
    @tool
    def get_user_location() -> ToolExecutionResponse:
        """
        Get the user's last shared location.
        Returns the most recent location with coordinates, platform, timestamp, and optional name.
        If user has not shared location, returns a message suggesting to request it.

        Returns:
            ToolExecutionResponse with location data or suggestion to request location
        """
        try:
            location = user_service.get_user_last_location(user_id)

            if not location:
                return ToolExecutionResponse(
                    status="success",
                    result={
                        "has_location": False,
                        "message": "User has not shared their location yet. You should ask them to share their location using request_location parameter in your reply.",
                        "suggestion": "Use request_location=True in your next message to ask the user for their location."
                    }
                )

            # Format timestamp nicely
            timestamp = location.get("timestamp")
            if timestamp:
                timestamp_str = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
            else:
                timestamp_str = None

            return ToolExecutionResponse(
                status="success",
                result={
                    "has_location": True,
                    "location": {
                        "latitude": location.get("latitude"),
                        "longitude": location.get("longitude"),
                        "name": location.get("name"),
                        "platform": location.get("platform"),
                        "timestamp": timestamp_str
                    }
                }
            )
        except Exception as e:
            logger.error(f"Failed to get user location: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_user_location",
                exception=e,
                integration="user_preferences"
            )

    @tool
    def get_user_location_history(limit: int = 10) -> ToolExecutionResponse:
        """
        Get the user's location history (most recent first).
        Returns up to 'limit' recent locations with coordinates, platform, timestamp, and optional name.
        If user has not shared any locations, returns a message suggesting to request it.

        Args:
            limit: Maximum number of locations to return (default 10, max 100)

        Returns:
            ToolExecutionResponse with location history or suggestion to request location
        """
        try:
            # Validate limit
            if limit < 1:
                limit = 10
            if limit > 100:
                limit = 100

            history = user_service.get_user_location_history(user_id, limit=limit)

            if not history:
                return ToolExecutionResponse(
                    status="success",
                    result={
                        "has_history": False,
                        "count": 0,
                        "message": "User has not shared their location yet. You should ask them to share their location using request_location parameter in your reply.",
                        "suggestion": "Use request_location=True in your next message to ask the user for their location."
                    }
                )

            # Format locations
            formatted_history = []
            for loc in history:
                timestamp = loc.get("timestamp")
                if timestamp:
                    timestamp_str = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
                else:
                    timestamp_str = None

                formatted_history.append({
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                    "name": loc.get("name"),
                    "platform": loc.get("platform"),
                    "timestamp": timestamp_str
                })

            return ToolExecutionResponse(
                status="success",
                result={
                    "has_history": True,
                    "count": len(formatted_history),
                    "locations": formatted_history
                }
            )
        except Exception as e:
            logger.error(f"Failed to get user location history: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_user_location_history",
                exception=e,
                integration="user_preferences",
                context={"limit": limit}
            )

    all_tools = [
        add_user_preference_annotation,
        set_assistant_name,
        set_timezone,
        set_language_response,
        delete_user_preference_annotations,
        get_user_location,
        get_user_location_history,
    ]
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools
