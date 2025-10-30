from datetime import datetime, timezone, timedelta
from typing import Union
from zoneinfo import ZoneInfo # Use this for Python 3.9+
def nyc_to_utc(nyc_dt: datetime, timezone: str|ZoneInfo = "America/New_York") -> datetime:
    """
    Converts a naive datetime object from NYC time to UTC.

    This function correctly handles both Standard Time (EST, UTC-5) and
    Daylight Saving Time (EDT, UTC-4) by using the 'America/New_York'
    timezone database.
    """
    # Define the New York timezone using the IANA database
    if isinstance(timezone, str):
        zoneinfo = to_ZoneInfo(timezone)
    else:
        zoneinfo = timezone
    
    # Localize the naive datetime by applying the NYC timezone.
    # This step correctly determines whether the datetime falls in EST or EDT.
    aware_nyc_dt = nyc_dt.replace(tzinfo=zoneinfo)
    
    # Convert the timezone-aware NYC datetime to UTC
    utc_dt = aware_nyc_dt.astimezone(timezone.utc)
    
    return utc_dt

def to_ZoneInfo(timezone_name: str) -> ZoneInfo:
    """
    Converts a timezone name string to a ZoneInfo object.
    """
    try:
        return ZoneInfo(timezone_name)
    except Exception as e:
        return ZoneInfo("America/New_York")  # Fallback to NYC

def to_rfc3339(dt: Union[datetime, str]) -> str:
    if isinstance(dt, str):
        # assume already RFC-3339 (defensive)
        return dt
    if dt.tzinfo is None:
        # choose a policy: assume UTC, or attach the user’s tz before this
        dt = dt.replace(tzinfo=timezone.utc)
    # Example: use UTC with trailing Z
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")