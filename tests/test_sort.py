from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from clashctl_py.models import (
    Connection,
    History,
    Metadata,
    Proxy,
    ProxyType,
    Rule,
    RuleType,
)
from clashctl_py.state import (
    ConnectionWithSpeed,
    ConnSort,
    ConnSortBy,
    Order,
    ProxySort,
    ProxySortBy,
    RuleSort,
    RuleSortBy,
)

# --- helpers ---------------------------------------------------------------


def _proxy(name: str, ptype: ProxyType, delay: int | None) -> tuple[str, Proxy]:
    history = []
    if delay is not None:
        history.append(History(time=datetime(2024, 1, 1, tzinfo=UTC), delay=delay))
    return name, Proxy(type=ptype, history=history)


def _conn(
    cid: str,
    *,
    host: str = "example.com",
    upload: int = 0,
    download: int = 0,
    rule: RuleType = RuleType.Match,
    chains: list[str] | None = None,
    start: datetime | None = None,
    src_ip: str = "10.0.0.1",
    src_port: str = "10000",
    dst_ip: str = "1.1.1.1",
    dst_port: str = "443",
    type_: str = "HTTP",
) -> Connection:
    return Connection(
        id=cid,
        upload=upload,
        download=download,
        metadata=Metadata(
            type=type_,
            sourceIP=src_ip,
            source_port=src_port,
            destinationIP=dst_ip,
            destination_port=dst_port,
            host=host,
            network="tcp",
        ),
        rule=rule,
        rule_payload="",
        start=start or datetime(2024, 1, 1, tzinfo=UTC),
        chains=chains or [],
    )


def _cws(c: Connection, up: int = 0, down: int = 0) -> ConnectionWithSpeed:
    return ConnectionWithSpeed(c, upload_speed=up, download_speed=down)


# --- ProxySort -------------------------------------------------------------


def test_proxy_sort_by_delay_pushes_zero_and_none_to_end_in_asc() -> None:
    items = [
        _proxy("a", ProxyType.Vmess, 100),
        _proxy("b", ProxyType.Vmess, 0),  # failed
        _proxy("c", ProxyType.Vmess, 50),
        _proxy("d", ProxyType.Vmess, None),  # untested
    ]
    s = ProxySort(by=ProxySortBy.Delay, order=Order.Asc)
    names = [n for n, _ in s.apply(items)]
    assert names == ["c", "a", "b", "d"]


def test_proxy_sort_desc_reverses() -> None:
    items = [
        _proxy("a", ProxyType.Vmess, 100),
        _proxy("c", ProxyType.Vmess, 50),
    ]
    s = ProxySort(by=ProxySortBy.Delay, order=Order.Desc)
    names = [n for n, _ in s.apply(items)]
    assert names == ["a", "c"]


def test_proxy_sort_by_name() -> None:
    items = [
        _proxy("z", ProxyType.Vmess, 1),
        _proxy("a", ProxyType.Vmess, 2),
    ]
    s = ProxySort(by=ProxySortBy.Name, order=Order.Asc)
    assert [n for n, _ in s.apply(items)] == ["a", "z"]


def test_proxy_sort_cycle_returns_to_start() -> None:
    s = ProxySort()
    start = (s.by, s.order)
    for _ in range(6):
        s.next()
    assert (s.by, s.order) == start


def test_proxy_sort_prev_inverts_next() -> None:
    s = ProxySort()
    start = (s.by, s.order)
    s.next()
    s.prev()
    assert (s.by, s.order) == start


def test_proxy_sort_default_is_delay_asc() -> None:
    s = ProxySort()
    assert s.by is ProxySortBy.Delay
    assert s.order is Order.Asc


# --- RuleSort --------------------------------------------------------------


def test_rule_sort_by_payload() -> None:
    rules = [
        Rule(type=RuleType.Domain, payload="z.com", proxy="A"),
        Rule(type=RuleType.Domain, payload="a.com", proxy="B"),
    ]
    s = RuleSort(by=RuleSortBy.Payload, order=Order.Asc)
    assert [r.payload for r in s.apply(rules)] == ["a.com", "z.com"]


def test_rule_sort_by_proxy() -> None:
    rules = [
        Rule(type=RuleType.Domain, payload="x", proxy="zzz"),
        Rule(type=RuleType.Domain, payload="y", proxy="aaa"),
    ]
    s = RuleSort(by=RuleSortBy.Proxy, order=Order.Asc)
    assert [r.proxy for r in s.apply(rules)] == ["aaa", "zzz"]


def test_rule_sort_full_cycle() -> None:
    s = RuleSort()
    seen = set()
    for _ in range(6):
        seen.add((s.by, s.order))
        s.next()
    assert len(seen) == 6  # six unique (by, order) combinations


# --- ConnSort --------------------------------------------------------------


def test_conn_sort_by_host() -> None:
    items = [
        _cws(_conn("1", host="zebra.io")),
        _cws(_conn("2", host="alpha.io")),
    ]
    s = ConnSort(by=ConnSortBy.Host, order=Order.Asc)
    assert [c.connection.id for c in s.apply(items)] == ["2", "1"]


def test_conn_sort_by_download_speed() -> None:
    items = [
        _cws(_conn("1"), down=100),
        _cws(_conn("2"), down=500),
        _cws(_conn("3"), down=10),
    ]
    s = ConnSort(by=ConnSortBy.DownSpeed, order=Order.Desc)
    assert [c.connection.id for c in s.apply(items)] == ["2", "1", "3"]


def test_conn_sort_by_time_desc_newest_first() -> None:
    base = datetime(2024, 6, 1, tzinfo=UTC)
    items = [
        _cws(_conn("old", start=base)),
        _cws(_conn("mid", start=base + timedelta(seconds=10))),
        _cws(_conn("new", start=base + timedelta(seconds=20))),
    ]
    s = ConnSort(by=ConnSortBy.Time, order=Order.Desc)
    assert [c.connection.id for c in s.apply(items)] == ["new", "mid", "old"]


def test_conn_sort_by_chains_joins_for_compare() -> None:
    items = [
        _cws(_conn("1", chains=["B", "C"])),
        _cws(_conn("2", chains=["A", "Z"])),
    ]
    s = ConnSort(by=ConnSortBy.Chains, order=Order.Asc)
    assert [c.connection.id for c in s.apply(items)] == ["2", "1"]


def test_conn_sort_by_src_uses_port_int() -> None:
    items = [
        _cws(_conn("1", src_ip="10.0.0.1", src_port="9999")),
        _cws(_conn("2", src_ip="10.0.0.1", src_port="100")),
    ]
    s = ConnSort(by=ConnSortBy.Src, order=Order.Asc)
    # Same IP, port 100 < port 9999.
    assert [c.connection.id for c in s.apply(items)] == ["2", "1"]


def test_conn_sort_full_cycle() -> None:
    s = ConnSort()
    seen = []
    for _ in range(22):  # 11 keys * 2 orders
        seen.append((s.by, s.order))
        s.next()
    assert len(set(seen)) == 22


def test_conn_sort_default_is_time_desc() -> None:
    s = ConnSort()
    assert s.by is ConnSortBy.Time
    assert s.order is Order.Desc


@pytest.mark.parametrize(
    "by",
    [
        ConnSortBy.Host,
        ConnSortBy.Down,
        ConnSortBy.Up,
        ConnSortBy.DownSpeed,
        ConnSortBy.UpSpeed,
        ConnSortBy.Chains,
        ConnSortBy.Rule,
        ConnSortBy.Time,
        ConnSortBy.Src,
        ConnSortBy.Dest,
        ConnSortBy.Type,
    ],
)
def test_conn_sort_every_key_is_callable(by: ConnSortBy) -> None:
    """Smoke-test that key() returns something comparable for every variant."""
    items = [_cws(_conn("a"), up=1, down=2), _cws(_conn("b"), up=3, down=4)]
    s = ConnSort(by=by, order=Order.Asc)
    out = s.apply(items)
    assert len(out) == 2
