from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from clashctl.models import (
    ClashConfig,
    Connections,
    Delay,
    LogLevel,
    LogLine,
    Mode,
    Proxies,
    Proxy,
    ProxyType,
    Rule,
    Rules,
    RuleType,
    Traffic,
    Version,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text())


# --- enum fallbacks --------------------------------------------------------


def test_proxy_type_unknown_falls_back() -> None:
    assert ProxyType("WireGuard") is ProxyType.Unknown
    assert ProxyType("vmess") is ProxyType.Vmess  # case-insensitive


def test_rule_type_unknown_falls_back() -> None:
    assert RuleType("FutureKind") is RuleType.Unknown
    assert RuleType("domain") is RuleType.Domain


def test_log_level_warn_alias() -> None:
    assert LogLevel("warn") is LogLevel.Warning
    assert LogLevel("warning") is LogLevel.Warning
    assert LogLevel("WARN") is LogLevel.Warning


def test_proxy_type_classification() -> None:
    assert ProxyType.Selector.is_group()
    assert ProxyType.URLTest.is_group()
    assert ProxyType.Direct.is_built_in()
    assert ProxyType.Vmess.is_normal()
    assert not ProxyType.Selector.is_normal()


# --- Version ---------------------------------------------------------------


def test_version_parses() -> None:
    v = Version.model_validate(_load("version.json"))
    assert v.version == "v1.18.0"
    assert v.premium is True


# --- Config (kebab-case) ---------------------------------------------------


def test_config_kebab_case() -> None:
    c = ClashConfig.model_validate(_load("configs.json"))
    assert c.port == 7890
    assert c.socks_port == 7891
    assert c.mixed_port == 7892
    assert c.mode is Mode.Rule
    assert c.log_level is LogLevel.Info
    assert c.allow_lan is False
    assert c.ipv6 is True


def test_config_round_trip_emits_kebab_keys() -> None:
    c = ClashConfig.model_validate(_load("configs.json"))
    dumped = c.model_dump(by_alias=True)
    assert "socks-port" in dumped
    assert "log-level" in dumped


# --- Proxies (envelope unwrapping) -----------------------------------------


def test_proxies_parses() -> None:
    raw = _load("proxies.json")
    assert isinstance(raw, dict)
    proxies = Proxies.model_validate(raw["proxies"])
    assert "GLOBAL" in proxies
    assert proxies["GLOBAL"].proxy_type is ProxyType.Selector
    assert proxies["JP-1"].proxy_type is ProxyType.Vmess
    assert proxies["JP-1"].latest_delay == 142
    assert proxies["US-1"].latest_delay == 0  # tested but unreachable


def test_proxies_iteration_helpers() -> None:
    raw = _load("proxies.json")
    assert isinstance(raw, dict)
    proxies = Proxies.model_validate(raw["proxies"])

    groups = {n for n, _ in proxies.groups()}
    assert groups == {"GLOBAL", "Auto", "Manual"}

    built_ins = {n for n, _ in proxies.built_ins()}
    assert built_ins == {"DIRECT", "REJECT"}

    normals = {n for n, _ in proxies.normal()}
    assert normals == {"JP-1", "US-1"}

    selectors = {n for n, _ in proxies.selectors()}
    assert selectors == {"GLOBAL", "Manual"}  # Auto is URLTest


def test_proxy_history_datetime() -> None:
    raw = _load("proxies.json")
    assert isinstance(raw, dict)
    proxies = Proxies.model_validate(raw["proxies"])
    h = proxies["JP-1"].history[0]
    assert isinstance(h.time, datetime)
    assert h.delay == 142


# --- Rules -----------------------------------------------------------------


def test_rules_parses() -> None:
    rules = Rules.model_validate(_load("rules.json"))
    assert len(rules.rules) == 5
    assert rules.rules[0].rule_type is RuleType.DomainSuffix
    assert rules.rules[-1].rule_type is RuleType.Match


def test_rules_frequency_excludes_direct_reject() -> None:
    rules = Rules.model_validate(_load("rules.json"))
    freq = rules.frequency()
    assert freq == {"Manual": 2, "Auto": 1}
    assert rules.most_frequent_proxy() == "Manual"


def test_rule_unknown_type() -> None:
    r = Rule.model_validate({"type": "Mystery", "payload": "x", "proxy": "Foo"})
    assert r.rule_type is RuleType.Unknown


# --- Connections (camelCase) -----------------------------------------------


def test_connections_parses() -> None:
    conns = Connections.model_validate(_load("connections.json"))
    assert conns.download_total == 12345678
    assert conns.upload_total == 234567
    assert len(conns.connections) == 1
    c = conns.connections[0]
    assert c.id == "abc-123"
    assert c.metadata.source_ip == "192.168.1.10"
    assert c.metadata.destination_port == "443"
    assert c.metadata.host == "www.google.com"
    assert c.rule is RuleType.DomainSuffix
    assert c.rule_payload == "google.com"
    assert c.chains == ["Manual", "JP-1"]
    assert isinstance(c.start, datetime)


# --- Traffic, Log, Delay ---------------------------------------------------


def test_traffic() -> None:
    assert Traffic.model_validate({"up": 10, "down": 20}) == Traffic(up=10, down=20)
    assert Traffic() == Traffic(up=0, down=0)


def test_logline_warn_aliasing() -> None:
    line = LogLine.model_validate({"type": "warn", "payload": "ok"})
    assert line.level is LogLevel.Warning
    assert line.payload == "ok"


def test_delay() -> None:
    d = Delay.model_validate({"delay": 137})
    assert d.delay == 137


# --- Optional Proxy fields -------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        {"type": "Direct", "history": []},
        {"type": "Selector", "history": [], "all": ["A", "B"], "now": "A"},
        {"type": "URLTest", "history": [], "all": ["A"]},
    ],
)
def test_proxy_optional_fields(data: dict) -> None:
    p = Proxy.model_validate(data)
    if data.get("now") is not None:
        assert p.now == data["now"]
    if data.get("all") is not None:
        assert p.all == data["all"]


# --- JSON fastpath enum coercion (regressions) -----------------------------


def test_proxy_unknown_type_via_json() -> None:
    p = Proxy.model_validate_json('{"type": "Hysteria", "history": []}')
    assert p.proxy_type is ProxyType.Unknown


def test_rule_unknown_type_via_json() -> None:
    r = Rule.model_validate_json('{"type": "FutureKind", "payload": "x", "proxy": "P"}')
    assert r.rule_type is RuleType.Unknown


def test_logline_warn_via_json() -> None:
    line = LogLine.model_validate_json('{"type": "warn", "payload": "ok"}')
    assert line.level is LogLevel.Warning
