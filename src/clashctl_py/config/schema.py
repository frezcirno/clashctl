"""TOML-backed user config.

Lives at `~/.config/clashctl/config.toml` (resolved via platformdirs).
This is *clashctl's own* config — distinct from Clash's `/configs` payload
(`models.config.ClashConfig`).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from clashctl_py.state.sort import (
    ConnSort,
    ConnSortBy,
    Order,
    ProxySort,
    ProxySortBy,
    RuleSort,
    RuleSortBy,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class Server(_StrictModel):
    """A Clash controller endpoint."""

    name: str
    url: str
    secret: str | None = None

    @field_validator("secret", mode="before")
    @classmethod
    def _empty_secret_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and v == "":
            return None
        return v

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"url must be http(s): {v!r}")
        if not parsed.netloc:
            raise ValueError(f"url missing host: {v!r}")
        return v


# --- per-list sort blocks --------------------------------------------------


class _SortBlock(_StrictModel):
    by: str
    order: Order = Order.Asc


class ProxySortConfig(_SortBlock):
    by: ProxySortBy = ProxySortBy.Delay  # type: ignore[assignment]


class RuleSortConfig(_SortBlock):
    by: RuleSortBy = RuleSortBy.Payload  # type: ignore[assignment]


class ConnSortConfig(_SortBlock):
    by: ConnSortBy = ConnSortBy.Time  # type: ignore[assignment]
    order: Order = Order.Desc


class SortsConfig(_StrictModel):
    proxies: ProxySortConfig = Field(default_factory=ProxySortConfig)
    rules: RuleSortConfig = Field(default_factory=RuleSortConfig)
    connections: ConnSortConfig = Field(default_factory=ConnSortConfig)

    def to_runtime(self) -> tuple[ProxySort, RuleSort, ConnSort]:
        return (
            ProxySort(by=self.proxies.by, order=self.proxies.order),
            RuleSort(by=self.rules.by, order=self.rules.order),
            ConnSort(by=self.connections.by, order=self.connections.order),
        )


# --- UI block --------------------------------------------------------------


class UiConfig(_StrictModel):
    test_url: str = "http://www.gstatic.com/generate_204"
    test_timeout_ms: int = 5000
    log_buffer: int = 2000
    traffic_history: int = 500
    refresh_slow_secs: float = 5.0
    refresh_fast_secs: float = 1.0
    sort: SortsConfig = Field(default_factory=SortsConfig)


# --- top-level ------------------------------------------------------------


class AppConfig(_StrictModel):
    """Persisted user config."""

    using: str | None = None
    servers: list[Server] = Field(default_factory=list)
    ui: UiConfig = Field(default_factory=UiConfig)

    def using_server(self) -> Server | None:
        if self.using is None:
            return None
        for s in self.servers:
            if s.url == self.using:
                return s
        return None

    def use(self, url: str) -> None:
        if not any(s.url == url for s in self.servers):
            raise ValueError(f"server not found: {url}")
        self.using = url

    def add_server(self, server: Server) -> None:
        if any(s.url == server.url for s in self.servers):
            raise ValueError(f"server already exists: {server.url}")
        self.servers.append(server)
        if self.using is None:
            self.using = server.url

    def remove_server(self, url: str) -> None:
        self.servers = [s for s in self.servers if s.url != url]
        if self.using == url:
            self.using = self.servers[0].url if self.servers else None
