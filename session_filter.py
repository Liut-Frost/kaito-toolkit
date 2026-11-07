"""
session_filter.py
ICT Killzone and Trading Session Filter.

Defines the core ICT session windows in New York time (America/New_York).
ICT setups carry the highest probability when formed inside an institutional
killzone, where market makers inject volume and deliver price to liquidity pools.

Standard ICT Killzones (EST / New York Time):
- Asian Session:       20:00 - 00:00 (accumulation / context, rarely trade)
- London Open:         02:00 - 05:00 (initial liquidity run, classic Judas swing)
- New York Open:       07:00 - 10:00 (major trend continuation or reversal)
- London Close:        10:00 - 12:00 (reversal or consolidation into the daily close)
- Silver Bullet AM:    10:00 - 11:00 (high-probability M5/M15 1:2 setup window)
- Silver Bullet PM:    14:00 - 15:00 (afternoon session 1:2 setup window)
"""

import pandas as pd
from datetime import datetime, time, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo


# Default killzone definitions (all times in America/New_York)
DEFAULT_KILLZONES = {
    "london_open": {
        "name": "London Open",
        "start": time(2, 0),
        "end": time(5, 0),
        "enabled": True,
    },
    "new_york_open": {
        "name": "New York Open",
        "start": time(7, 0),
        "end": time(10, 0),
        "enabled": True,
    },
    "london_close": {
        "name": "London Close",
        "start": time(10, 0),
        "end": time(12, 0),
        "enabled": True,
    },
    "silver_bullet_am": {
        "name": "Silver Bullet (AM)",
        "start": time(10, 0),
        "end": time(11, 0),
        "enabled": True,
    },
    "silver_bullet_pm": {
        "name": "Silver Bullet (PM)",
        "start": time(14, 0),
        "end": time(15, 0),
        "enabled": True,
    },
    "asian_session": {
        "name": "Asian Session",
        "start": time(20, 0),
        "end": time(23, 59),
        "enabled": False,  # Context only, disabled for signal entry by default
    },
}


def _to_ny_time(ts: Union[pd.Timestamp, datetime, str], tz_name: str = "America/New_York") -> datetime:
    """Converts any timestamp to America/New_York datetime."""
    if isinstance(ts, str):
        ts = pd.to_datetime(ts)

    if isinstance(ts, pd.Timestamp):
        if ts.tz is None:
            # Assume UTC if not timezone-aware
            ts = ts.tz_localize("UTC")
        ny_ts = ts.tz_convert(tz_name)
        return ny_ts.to_pydatetime()

    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(ZoneInfo(tz_name))

    raise ValueError(f"Unsupported timestamp type: {type(ts)}")


def is_in_killzone(timestamp: Union[pd.Timestamp, datetime, str],
                   killzone_config: Optional[dict] = None) -> tuple[bool, str]:
    """
    Checks if a timestamp falls inside any enabled ICT killzone.

    Args:
        timestamp: Timestamp of the candle / setup event.
        killzone_config: Optional dict overriding DEFAULT_KILLZONES.

    Returns:
        (is_active: bool, active_zone_name: str)
        If in a killzone: (True, "London Open")
        If outside all:   (False, "Outside killzones")
    """
    ny_dt = _to_ny_time(timestamp)
    t = ny_dt.time()

    zones = killzone_config or DEFAULT_KILLZONES

    for key, zone in zones.items():
        if not zone.get("enabled", True):
            continue

        start = zone["start"]
        end = zone["end"]

        # Parse string times if loaded from JSON config
        if isinstance(start, str):
            h, m = map(int, start.split(":"))
            start = time(h, m)
        if isinstance(end, str):
            h, m = map(int, end.split(":"))
            end = time(h, m)

        # Standard range check (handles both same-day and cross-midnight if needed)
        if start <= end:
            if start <= t <= end:
                return True, zone["name"]
        else:
            # Crosses midnight (e.g. 20:00 to 02:00)
            if t >= start or t <= end:
                return True, zone["name"]

    return False, "Outside killzones"


def get_active_killzones(timestamp: Union[pd.Timestamp, datetime, str],
                         killzone_config: Optional[dict] = None) -> list[str]:
    """Returns a list of all currently active killzone names for the given timestamp."""
    ny_dt = _to_ny_time(timestamp)
    t = ny_dt.time()

    zones = killzone_config or DEFAULT_KILLZONES
    active = []

    for key, zone in zones.items():
        if not zone.get("enabled", True):
            continue

        start = zone["start"]
        end = zone["end"]

        if isinstance(start, str):
            h, m = map(int, start.split(":"))
            start = time(h, m)
        if isinstance(end, str):
            h, m = map(int, end.split(":"))
            end = time(h, m)

        if start <= end:
            if start <= t <= end:
                active.append(zone["name"])
        else:
            if t >= start or t <= end:
                active.append(zone["name"])

    return active
