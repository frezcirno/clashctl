from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from clashctl.utils.duration import humanize_seconds, humanize_since


@pytest.mark.parametrize(
    "secs, expected",
    [
        (0, "00:00"),
        (1, "00:01"),
        (59, "00:59"),
        (60, "01:00"),
        (61, "01:01"),
        (3599, "59:59"),
        (3600, "1:00:00"),
        (3661, "1:01:01"),
        (24 * 3600, "24:00:00"),
        (-5, "00:00"),  # negative clamped to zero
    ],
)
def test_humanize_seconds(secs: float, expected: str) -> None:
    assert humanize_seconds(secs) == expected


def test_humanize_since_uses_passed_now() -> None:
    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    now = start + timedelta(seconds=125)
    assert humanize_since(start, now=now) == "02:05"


def test_humanize_since_assumes_utc_when_naive() -> None:
    start = datetime(2024, 1, 1, 0, 0, 0)  # naive
    now = datetime(2024, 1, 1, 0, 0, 30, tzinfo=UTC)
    assert humanize_since(start, now=now) == "00:30"
