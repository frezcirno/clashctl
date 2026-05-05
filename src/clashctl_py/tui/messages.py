"""Textual `Message` subclasses used by Pollers to deliver updates to the App.

Pollers are pure asyncio code; they don't import Textual themselves. They
post messages via a `post: Callable[[Message], None]` injected by the App,
which is bound to `App.post_message` at runtime.
"""

from __future__ import annotations

from textual.message import Message

from clashctl_py.models import (
    ClashConfig,
    Connections,
    LogLine,
    Proxies,
    Rules,
    Traffic,
    Version,
)


class VersionUpdate(Message):
    def __init__(self, version: Version) -> None:
        super().__init__()
        self.version = version


class ConfigUpdate(Message):
    def __init__(self, config: ClashConfig) -> None:
        super().__init__()
        self.config = config


class ProxiesUpdate(Message):
    def __init__(self, proxies: Proxies) -> None:
        super().__init__()
        self.proxies = proxies


class RulesUpdate(Message):
    def __init__(self, rules: Rules) -> None:
        super().__init__()
        self.rules = rules


class ConnectionsUpdate(Message):
    def __init__(self, connections: Connections) -> None:
        super().__init__()
        self.connections = connections


class TrafficUpdate(Message):
    def __init__(self, traffic: Traffic) -> None:
        super().__init__()
        self.traffic = traffic


class LogUpdate(Message):
    def __init__(self, line: LogLine) -> None:
        super().__init__()
        self.line = line


class NetworkError(Message):
    """Posted whenever a poll round or a stream attempt fails."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__()
        self.source = source
        self.detail = detail


class StreamReconnect(Message):
    """Posted when a streaming endpoint reconnects after a failure."""

    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source


# --- widget-originated requests handled by the App -----------------------


class TestLatencyRequest(Message):
    """Bubbled from the proxy tree when the user presses `t` on a group."""

    __test__ = False  # pytest: not a test class despite the "Test" prefix.

    def __init__(self, group: str) -> None:
        super().__init__()
        self.group = group


class ApplySelectionRequest(Message):
    """Bubbled from the proxy tree when the user picks a member of a Selector."""

    def __init__(self, group: str, proxy: str) -> None:
        super().__init__()
        self.group = group
        self.proxy = proxy
