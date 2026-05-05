"""Compact HH:MM:SS / MM:SS duration formatting for the Conns tab."""

from __future__ import annotations

from datetime import UTC, datetime


def humanize_seconds(seconds: float) -> str:
    """Render a non-negative duration as `H:MM:SS` (or `MM:SS` if < 1h)."""
    if seconds < 0:
        seconds = 0
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def humanize_since(start: datetime, *, now: datetime | None = None) -> str:
    """Format `now - start` using `humanize_seconds`."""
    if now is None:
        now = datetime.now(tz=UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    delta = (now - start).total_seconds()
    return humanize_seconds(delta)
