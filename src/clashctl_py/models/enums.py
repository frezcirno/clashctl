from __future__ import annotations

from enum import StrEnum
from typing import Any


class ProxyType(StrEnum):
    Direct = "Direct"
    Reject = "Reject"
    Selector = "Selector"
    URLTest = "URLTest"
    Fallback = "Fallback"
    LoadBalance = "LoadBalance"
    Shadowsocks = "Shadowsocks"
    Vmess = "Vmess"
    ShadowsocksR = "ShadowsocksR"
    Http = "Http"
    Snell = "Snell"
    Trojan = "Trojan"
    Socks5 = "Socks5"
    Relay = "Relay"
    Unknown = "Unknown"

    @classmethod
    def _missing_(cls, value: Any) -> ProxyType:
        if isinstance(value, str):
            low = value.lower()
            for m in cls:
                if m.value.lower() == low:
                    return m
        return cls.Unknown

    def is_group(self) -> bool:
        return self in {
            ProxyType.Selector,
            ProxyType.URLTest,
            ProxyType.Fallback,
            ProxyType.LoadBalance,
            ProxyType.Relay,
        }

    def is_built_in(self) -> bool:
        return self in {ProxyType.Direct, ProxyType.Reject}

    def is_normal(self) -> bool:
        return self in {
            ProxyType.Shadowsocks,
            ProxyType.Vmess,
            ProxyType.ShadowsocksR,
            ProxyType.Http,
            ProxyType.Snell,
            ProxyType.Trojan,
            ProxyType.Socks5,
        }

    def is_selector(self) -> bool:
        return self is ProxyType.Selector


class RuleType(StrEnum):
    Domain = "Domain"
    DomainSuffix = "DomainSuffix"
    DomainKeyword = "DomainKeyword"
    GeoIP = "GeoIP"
    IPCIDR = "IPCIDR"
    SrcIPCIDR = "SrcIPCIDR"
    SrcPort = "SrcPort"
    DstPort = "DstPort"
    Process = "Process"
    Match = "Match"
    Direct = "Direct"
    Reject = "Reject"
    Unknown = "Unknown"

    @classmethod
    def _missing_(cls, value: Any) -> RuleType:
        if isinstance(value, str):
            low = value.lower()
            for m in cls:
                if m.value.lower() == low:
                    return m
        return cls.Unknown


class Mode(StrEnum):
    Global = "global"
    Rule = "rule"
    Direct = "direct"

    @classmethod
    def _missing_(cls, value: Any) -> Mode:
        if isinstance(value, str):
            low = value.lower()
            for m in cls:
                if m.value == low:
                    return m
        return cls.Rule


class LogLevel(StrEnum):
    Error = "error"
    Warning = "warning"
    Info = "info"
    Debug = "debug"

    @classmethod
    def _missing_(cls, value: Any) -> LogLevel:
        if isinstance(value, str):
            low = value.lower()
            if low in {"warn", "warning"}:
                return cls.Warning
            for m in cls:
                if m.value == low:
                    return m
        return cls.Info
