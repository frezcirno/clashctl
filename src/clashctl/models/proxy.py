from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field, RootModel, field_validator

from clashctl.models.base import ClashModel
from clashctl.models.enums import ProxyType


class History(ClashModel):
    time: datetime
    delay: int


class Proxy(ClashModel):
    proxy_type: ProxyType = Field(alias="type")
    history: List[History] = Field(default_factory=list)
    udp: Optional[bool] = None
    all: Optional[List[str]] = None
    now: Optional[str] = None

    @field_validator("proxy_type", mode="before")
    @classmethod
    def _coerce_proxy_type(cls, v: Any) -> Any:
        # Pydantic's JSON-fastpath skips Enum._missing_; route through it.
        return ProxyType(v) if isinstance(v, str) else v

    @field_validator("history", mode="before")
    @classmethod
    def _coerce_history(cls, v: Any) -> Any:
        return [] if v is None else v

    @property
    def latest_delay(self) -> Optional[int]:
        if not self.history:
            return None
        return self.history[0].delay


class Proxies(RootModel[Dict[str, Proxy]]):
    """Wrapper for `GET /proxies` response: `{"proxies": {...}}`."""

    root: Dict[str, Proxy] = Field(default_factory=dict)

    def __getitem__(self, name: str) -> Proxy:
        return self.root[name]

    def __contains__(self, name: object) -> bool:
        return name in self.root

    def __iter__(self) -> Iterator[Tuple[str, Proxy]]:  # type: ignore[override]
        return iter(self.root.items())

    def __len__(self) -> int:
        return len(self.root)

    def items(self) -> Iterator[Tuple[str, Proxy]]:
        return iter(self.root.items())

    def get(self, name: str) -> Optional[Proxy]:
        return self.root.get(name)

    def groups(self) -> Iterator[Tuple[str, Proxy]]:
        for n, p in self.root.items():
            if p.proxy_type.is_group():
                yield n, p

    def normal(self) -> Iterator[Tuple[str, Proxy]]:
        for n, p in self.root.items():
            if p.proxy_type.is_normal():
                yield n, p

    def built_ins(self) -> Iterator[Tuple[str, Proxy]]:
        for n, p in self.root.items():
            if p.proxy_type.is_built_in():
                yield n, p

    def selectors(self) -> Iterator[Tuple[str, Proxy]]:
        for n, p in self.root.items():
            if p.proxy_type.is_selector():
                yield n, p


class ProxiesEnvelope(ClashModel):
    """The actual `/proxies` envelope; we usually unwrap it."""

    proxies: Dict[str, Proxy]


class Delay(ClashModel):
    delay: int
