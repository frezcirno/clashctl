from __future__ import annotations

import pytest

from clashctl_py.models import LogLevel, RuleType
from clashctl_py.tui.theme import latency_color, log_level_color, rule_type_color


@pytest.mark.parametrize(
    "delay, expected",
    [
        (None, "grey50"),  # untested
        (0, "red"),  # tested → unreachable
        (1, "green"),
        (200, "green"),
        (201, "yellow"),
        (400, "yellow"),
        (401, "red"),
        (5000, "red"),
    ],
)
def test_latency_thresholds(delay: int | None, expected: str) -> None:
    assert latency_color(delay) == expected


def test_log_level_colors() -> None:
    assert log_level_color(LogLevel.Error) == "red"
    assert log_level_color(LogLevel.Warning) == "yellow"
    assert log_level_color(LogLevel.Info) == "green"
    assert log_level_color(LogLevel.Debug) == "blue"


@pytest.mark.parametrize(
    "rt, color",
    [
        (RuleType.Domain, "green"),
        (RuleType.DomainSuffix, "green"),
        (RuleType.GeoIP, "yellow"),
        (RuleType.IPCIDR, "yellow"),
        (RuleType.Match, "blue"),
        (RuleType.Reject, "red"),
        (RuleType.Unknown, "grey50"),
    ],
)
def test_rule_type_colors(rt: RuleType, color: str) -> None:
    assert rule_type_color(rt) == color
