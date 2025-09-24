from datetime import datetime
from typing import List, Dict, Any
import pytz

from langchain_core.tools import tool
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

def create_preference_tools(user_id: str) -> list:
    """Create basic user preference tools bound to a specific user_id."""

    @tool
    def add_user_preference_annotation(new_preference_text: List[str]) -> Dict[str, Any]:
        """
        Add one or more preference annotations for the user.
        this is for when the user mentions a new preference in conversation, and we want to remember it for future interactions.
        - If the 'annotations' field doesn't exist, it will be created as a list[str].
        - If it exists, new items are merged (de-duplicated, order preserved).
        Args:
            new_preference_text: List of annotation strings to add.
        Returns:
            { "ok": bool, "message": str, "updated": { ...preference doc subset... } }
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
            ok = user_service.add_new_preference_annotations(user_id, payload)
            return {
                "ok": bool(ok),
                "message": "Annotations updated.",
                "updated": {"annotations": merged, "updated_at": payload["updated_at"]},
            }
        except Exception as e:
            return {"ok": False, "message": f"Failed to add annotations"}

    @tool
    def set_assistant_name(assistant_name: str) -> Dict[str, Any]:
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
            return {
                "ok": bool(ok),
                "message": "Assistant name updated.",
                "updated": {"assistant_name": name, "updated_at": payload["updated_at"]},
            }
        except Exception as e:
            return {"ok": False, "message": f"Failed to update assistant name: {e}"}

    @tool
    def set_timezone(timezone_name: str) -> Dict[str, Any]:
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
            return {
                "ok": bool(ok),
                "message": "Timezone updated.",
                "updated": {"timezone": tz, "updated_at": payload["updated_at"]},
            }
        except Exception as e:
            return {"ok": False, "message": f"Failed to update timezone: {e}"}

    @tool
    def set_language_response(language_code: str) -> Dict[str, Any]:
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
            return {
                "ok": bool(ok),
                "message": "Language preference updated.",
                "updated": {"language_responses": code, "updated_at": payload["updated_at"]},
            }
        except Exception as e:
            return {"ok": False, "message": f"Failed to update language: {e}"}

    return [
        add_user_preference_annotation,
        set_assistant_name,
        set_timezone,
        set_language_response,
    ]
