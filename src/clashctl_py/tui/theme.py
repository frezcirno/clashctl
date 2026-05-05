"""Color and threshold constants used across TUI widgets.

Latency thresholds match the Rust implementation:
- 0           → unreachable / failed test
- 1..200 ms   → green
- 201..400 ms → yellow
- 401+ ms     → red
"""

from __future__ import annotations

from clashctl_py.models import LogLevel, RuleType

# --- log level colors ----------------------------------------------------


_LOG_LEVEL_COLORS = {
    LogLevel.Error: "red",
    LogLevel.Warning: "yellow",
    LogLevel.Info: "green",
    LogLevel.Debug: "blue",
}


def log_level_color(level: LogLevel) -> str:
    return _LOG_LEVEL_COLORS.get(level, "white")


# --- latency colors ------------------------------------------------------


def latency_color(delay_ms: int | None) -> str:
    """Return a Rich/Textual color name for a delay measurement.

    `None` means untested (no history); 0 means tested-but-unreachable.
    """
    if delay_ms is None:
        return "grey50"
    if delay_ms == 0:
        return "red"
    if delay_ms <= 200:
        return "green"
    if delay_ms <= 400:
        return "yellow"
    return "red"


# --- rule type colors ----------------------------------------------------


_RULE_TYPE_COLORS: dict[RuleType, str] = {
    RuleType.Domain: "green",
    RuleType.DomainSuffix: "green",
    RuleType.DomainKeyword: "green",
    RuleType.GeoIP: "yellow",
    RuleType.IPCIDR: "yellow",
    RuleType.SrcIPCIDR: "yellow",
    RuleType.SrcPort: "yellow",
    RuleType.DstPort: "yellow",
    RuleType.Process: "yellow",
    RuleType.Match: "blue",
    RuleType.Direct: "blue",
    RuleType.Reject: "red",
    RuleType.Unknown: "grey50",
}


def rule_type_color(rt: RuleType) -> str:
    return _RULE_TYPE_COLORS.get(rt, "white")
