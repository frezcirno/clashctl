"""Sort definitions for the three list-bearing TUI tabs.

Each sort class exposes:
- `by` and `order` fields
- `next()` / `prev()` to cycle through (by, order) pairs
- `key()` returning a stable comparable for use with `sorted(..., key=...)`
- `apply(items)` convenience wrapper

The cycle order matches the Rust implementation: each `by` value visits
`asc` then `desc` before advancing to the next `by`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar

from clashctl_py.models import Proxy, Rule

if TYPE_CHECKING:
    from clashctl_py.state.speed import ConnectionWithSpeed

T = TypeVar("T")


class Order(StrEnum):
    Asc = "asc"
    Desc = "desc"
    Off = "off"


_HEADER_CYCLE: tuple[Order, Order, Order] = (Order.Asc, Order.Desc, Order.Off)


def _next_header_order(order: Order) -> Order:
    """Asc → Desc → Off → Asc, used for header-click cycling."""
    i = _HEADER_CYCLE.index(order) if order in _HEADER_CYCLE else -1
    return _HEADER_CYCLE[(i + 1) % len(_HEADER_CYCLE)]


# --- ProxySort -------------------------------------------------------------


class ProxySortBy(StrEnum):
    Name = "name"
    Type = "type"
    Delay = "delay"


_PROXY_CYCLE: list[tuple[ProxySortBy, Order]] = [
    (ProxySortBy.Name, Order.Asc),
    (ProxySortBy.Name, Order.Desc),
    (ProxySortBy.Type, Order.Asc),
    (ProxySortBy.Type, Order.Desc),
    (ProxySortBy.Delay, Order.Asc),
    (ProxySortBy.Delay, Order.Desc),
]


@dataclass
class ProxySort:
    by: ProxySortBy = ProxySortBy.Delay
    order: Order = Order.Asc

    def next(self) -> None:
        if self.order is Order.Off:
            self.order = Order.Asc
            return
        i = _PROXY_CYCLE.index((self.by, self.order))
        self.by, self.order = _PROXY_CYCLE[(i + 1) % len(_PROXY_CYCLE)]

    def prev(self) -> None:
        if self.order is Order.Off:
            self.order = Order.Desc
            return
        i = _PROXY_CYCLE.index((self.by, self.order))
        self.by, self.order = _PROXY_CYCLE[(i - 1) % len(_PROXY_CYCLE)]

    def cycle_by(self, by: ProxySortBy) -> None:
        """Header-click cycling: switch to `by` (asc), or advance asc→desc→off."""
        if self.by is by:
            self.order = _next_header_order(self.order)
        else:
            self.by = by
            self.order = Order.Asc

    def key(self, item: tuple[str, Proxy]) -> tuple[Any, ...]:
        name, proxy = item
        if self.by is ProxySortBy.Name:
            primary: Any = name
        elif self.by is ProxySortBy.Type:
            primary = proxy.proxy_type.value
        else:  # Delay
            d = proxy.latest_delay
            # Push 0-delay (failed) and None (untested) to the end of asc lists.
            if d is None:
                primary = (2, 0)
            elif d == 0:
                primary = (1, 0)
            else:
                primary = (0, d)
        # Tie-break by name so output is stable.
        return (primary, name)

    def apply(self, items: Iterable[tuple[str, Proxy]]) -> list[tuple[str, Proxy]]:
        return _ordered(list(items), self.key, self.order)


# --- RuleSort --------------------------------------------------------------


class RuleSortBy(StrEnum):
    Payload = "payload"
    Type = "type"
    Proxy = "proxy"


_RULE_CYCLE: list[tuple[RuleSortBy, Order]] = [
    (RuleSortBy.Payload, Order.Asc),
    (RuleSortBy.Payload, Order.Desc),
    (RuleSortBy.Type, Order.Asc),
    (RuleSortBy.Type, Order.Desc),
    (RuleSortBy.Proxy, Order.Asc),
    (RuleSortBy.Proxy, Order.Desc),
]


@dataclass
class RuleSort:
    by: RuleSortBy = RuleSortBy.Payload
    order: Order = Order.Asc

    def next(self) -> None:
        if self.order is Order.Off:
            self.order = Order.Asc
            return
        i = _RULE_CYCLE.index((self.by, self.order))
        self.by, self.order = _RULE_CYCLE[(i + 1) % len(_RULE_CYCLE)]

    def prev(self) -> None:
        if self.order is Order.Off:
            self.order = Order.Desc
            return
        i = _RULE_CYCLE.index((self.by, self.order))
        self.by, self.order = _RULE_CYCLE[(i - 1) % len(_RULE_CYCLE)]

    def cycle_by(self, by: RuleSortBy) -> None:
        """Header-click cycling: switch to `by` (asc), or advance asc→desc→off."""
        if self.by is by:
            self.order = _next_header_order(self.order)
        else:
            self.by = by
            self.order = Order.Asc

    def key(self, r: Rule) -> tuple[Any, ...]:
        if self.by is RuleSortBy.Payload:
            primary: Any = r.payload
        elif self.by is RuleSortBy.Type:
            primary = r.rule_type.value
        else:
            primary = r.proxy
        return (primary, r.payload, r.proxy)

    def apply(self, items: Iterable[Rule]) -> list[Rule]:
        return _ordered(list(items), self.key, self.order)


# --- ConnSort (the original Rust version was todo!()) ----------------------


class ConnSortBy(StrEnum):
    Host = "host"
    Down = "down"
    Up = "up"
    DownSpeed = "down_speed"
    UpSpeed = "up_speed"
    Chains = "chains"
    Rule = "rule"
    Time = "time"
    Src = "src"
    Dest = "dest"
    Type = "type"


_CONN_BY_LIST = list(ConnSortBy)
_CONN_CYCLE: list[tuple[ConnSortBy, Order]] = [
    (b, o) for b in _CONN_BY_LIST for o in (Order.Asc, Order.Desc)
]


@dataclass
class ConnSort:
    by: ConnSortBy = ConnSortBy.Time
    order: Order = Order.Desc

    def next(self) -> None:
        if self.order is Order.Off:
            self.order = Order.Asc
            return
        i = _CONN_CYCLE.index((self.by, self.order))
        self.by, self.order = _CONN_CYCLE[(i + 1) % len(_CONN_CYCLE)]

    def prev(self) -> None:
        if self.order is Order.Off:
            self.order = Order.Desc
            return
        i = _CONN_CYCLE.index((self.by, self.order))
        self.by, self.order = _CONN_CYCLE[(i - 1) % len(_CONN_CYCLE)]

    def cycle_by(self, by: ConnSortBy) -> None:
        """Header-click cycling: switch to `by` (asc), or advance asc→desc→off."""
        if self.by is by:
            self.order = _next_header_order(self.order)
        else:
            self.by = by
            self.order = Order.Asc

    def key(self, cws: ConnectionWithSpeed) -> tuple[Any, ...]:
        c = cws.connection
        m = c.metadata
        if self.by is ConnSortBy.Host:
            primary: Any = m.host
        elif self.by is ConnSortBy.Down:
            primary = c.download
        elif self.by is ConnSortBy.Up:
            primary = c.upload
        elif self.by is ConnSortBy.DownSpeed:
            primary = cws.download_speed
        elif self.by is ConnSortBy.UpSpeed:
            primary = cws.upload_speed
        elif self.by is ConnSortBy.Chains:
            primary = " > ".join(c.chains)
        elif self.by is ConnSortBy.Rule:
            primary = c.rule.value
        elif self.by is ConnSortBy.Time:
            primary = c.start
        elif self.by is ConnSortBy.Src:
            primary = (m.source_ip, _port_int(m.source_port))
        elif self.by is ConnSortBy.Dest:
            primary = (m.host or m.destination_ip, _port_int(m.destination_port))
        else:  # Type
            primary = m.connection_type
        return (primary, c.id)

    def apply(self, items: Iterable[ConnectionWithSpeed]) -> list[ConnectionWithSpeed]:
        return _ordered(list(items), self.key, self.order)


def _port_int(p: str) -> int:
    try:
        return int(p)
    except ValueError:
        return 0


# --- shared helpers --------------------------------------------------------


def _ordered(
    items: list[T],
    key: Any,
    order: Order,
) -> list[T]:
    if order is Order.Off:
        return items
    return sorted(items, key=key, reverse=order is Order.Desc)


# --- bundle for config -----------------------------------------------------


@dataclass
class Sorts:
    """Holder for the three sort cursors persisted in config."""

    proxies: ProxySort = field(default_factory=ProxySort)
    rules: RuleSort = field(default_factory=RuleSort)
    connections: ConnSort = field(default_factory=ConnSort)
