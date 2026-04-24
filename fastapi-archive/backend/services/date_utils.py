"""
services/date_utils.py — Shared date/time formatting helpers.
Identical to the Guesthouse version — only the module docstring changed.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def fmt_date(d: str) -> str:
    """Format YYYY-MM-DD → '12 Jun 2025' (cross-platform)."""
    if not d:
        return "—"
    dt = date.fromisoformat(d)
    return f"{dt.day} {dt.strftime('%b %Y')}"


def now_ist() -> str:
    """Return current time formatted in IST (Asia/Kolkata)."""
    now = datetime.now(IST)
    hour = now.hour % 12 or 12
    ampm = "AM" if now.hour < 12 else "PM"
    return f"{now.day} {now.strftime('%b %Y')}, {hour}:{now.strftime('%M')} {ampm}"
