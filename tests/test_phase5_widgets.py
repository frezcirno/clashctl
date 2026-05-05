"""Phase 5 widget tests: RuleListView and ConnectionListView via run_test()."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from textual.app import App, ComposeResult

from clashctl.models import (
    Connection,
    Connections,
    Metadata,
    Rule,
    Rules,
    RuleType,
)
from clashctl.state import (
    AppState,
    ConnSort,
    ConnSortBy,
    Order,
    RuleSort,
    RuleSortBy,
)
from clashctl.tui.widgets import ConnectionListView, RuleListView

# --- harness helpers ------------------------------------------------------


def _conn(
    cid: str,
    *,
    host: str = "example.com",
    upload: int = 0,
    download: int = 0,
    rule: RuleType = RuleType.Match,
    chains: list[str] | None = None,
    start_offset_secs: int = 0,
) -> Connection:
    return Connection(
        id=cid,
        upload=upload,
        download=download,
        metadata=Metadata(
            type="HTTP",
            sourceIP="10.0.0.1",
            source_port="1000",
            destinationIP="1.1.1.1",
            destination_port="443",
            host=host,
            network="tcp",
        ),
        rule=rule,
        rule_payload="",
        start=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(seconds=start_offset_secs),
        chains=chains or ["GLOBAL", "JP"],
    )


@pytest.fixture
def populated_state() -> AppState:
    s = AppState()
    s.apply_rules(
        Rules(
            rules=[
                Rule(type=RuleType.Domain, payload="z.com", proxy="ProxyA"),
                Rule(type=RuleType.DomainSuffix, payload="a.com", proxy="DIRECT"),
                Rule(type=RuleType.Match, payload="", proxy="ProxyB"),
            ]
        )
    )
    s.apply_connections(
        Connections(
            connections=[
                _conn("c1", host="zebra.io", download=1000, upload=10),
                _conn("c2", host="alpha.io", download=5000, upload=200),
            ],
            uploadTotal=210,
            downloadTotal=6000,
        )
    )
    return s


class _Harness(App[None]):
    def __init__(self, widget_cls, state: AppState) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self._widget_cls = widget_cls
        self._state = state

    def compose(self) -> ComposeResult:
        yield self._widget_cls(self._state)


# --- RuleListView ---------------------------------------------------------


async def test_rule_list_mounts_and_populates(populated_state: AppState) -> None:
    app = _Harness(RuleListView, populated_state)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        rl = app.query_one(RuleListView)
        assert rl.row_count == 3
        assert len(rl.columns) == 3


async def test_rule_list_default_sort_is_payload_asc(populated_state: AppState) -> None:
    app = _Harness(RuleListView, populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        rl = app.query_one(RuleListView)
        # Payload ascending → "" (Match), "a.com", "z.com" → first cell of first row is Match.
        # Column 0 is the rule type, column 1 is the payload.
        first_payload = rl.get_cell_at((0, 1))
        # Empty payload renders as "*"
        assert str(first_payload) == "*"


async def test_rule_list_sort_cycle(populated_state: AppState) -> None:
    app = _Harness(RuleListView, populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        rl = app.query_one(RuleListView)
        rl.focus()
        await pilot.pause()
        start = (rl._sort.by, rl._sort.order)
        # 6 (by, order) combinations should cycle back to start.
        for _ in range(6):
            await pilot.press("s")
            await pilot.pause(0.02)
        assert (rl._sort.by, rl._sort.order) == start


async def test_rule_list_reverse_sort_with_shift_s(populated_state: AppState) -> None:
    app = _Harness(RuleListView, populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        rl = app.query_one(RuleListView)
        rl.focus()
        await pilot.pause()
        start = (rl._sort.by, rl._sort.order)
        await pilot.press("s")
        await pilot.pause(0.02)
        # `pilot.press` accepts the binding-style modifier name. "S" alone is
        # the bare letter; "shift+s" is what the Binding declares.
        await pilot.press("shift+s")
        await pilot.pause(0.02)
        assert (rl._sort.by, rl._sort.order) == start


async def test_rule_list_hold_toggle(populated_state: AppState) -> None:
    app = _Harness(RuleListView, populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        rl = app.query_one(RuleListView)
        rl.focus()
        await pilot.pause()
        assert rl.hold is False
        await pilot.press("space")
        await pilot.pause(0.02)
        assert rl.hold is True
        await pilot.press("escape")
        await pilot.pause(0.02)
        assert rl.hold is False


async def test_rule_list_empty_state() -> None:
    """No rules yet should render an empty table without crashing."""
    app = _Harness(RuleListView, AppState())
    async with app.run_test() as pilot:
        await pilot.pause()
        rl = app.query_one(RuleListView)
        assert rl.row_count == 0


# --- ConnectionListView ---------------------------------------------------


async def test_conn_list_mounts_and_populates(populated_state: AppState) -> None:
    app = _Harness(ConnectionListView, populated_state)
    async with app.run_test(size=(160, 30)) as pilot:
        await pilot.pause()
        cl = app.query_one(ConnectionListView)
        assert cl.row_count == 2
        assert len(cl.columns) == 9


async def test_conn_list_sort_cycle_returns_to_start(populated_state: AppState) -> None:
    app = _Harness(ConnectionListView, populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        cl = app.query_one(ConnectionListView)
        cl.focus()
        await pilot.pause()
        start = (cl._sort.by, cl._sort.order)
        # 11 keys * 2 orders = 22 -> full cycle.
        for _ in range(22):
            await pilot.press("s")
            await pilot.pause(0.01)
        assert (cl._sort.by, cl._sort.order) == start


async def test_conn_list_hold_preserves_class(populated_state: AppState) -> None:
    app = _Harness(ConnectionListView, populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        cl = app.query_one(ConnectionListView)
        cl.focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause(0.02)
        assert cl.has_class("hold")
        await pilot.press("escape")
        await pilot.pause(0.02)
        assert not cl.has_class("hold")


async def test_conn_list_refresh_after_state_change(populated_state: AppState) -> None:
    app = _Harness(ConnectionListView, populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        cl = app.query_one(ConnectionListView)
        assert cl.row_count == 2
        # Drop one connection and refresh.
        populated_state.apply_connections(
            Connections(
                connections=[_conn("c1", host="zebra.io", download=2000, upload=20)],
                uploadTotal=20,
                downloadTotal=2000,
            )
        )
        cl.refresh_content()
        await pilot.pause()
        assert cl.row_count == 1


async def test_conn_list_sort_by_host_asc(populated_state: AppState) -> None:
    """Verify the sort actually reorders rows."""
    sort = ConnSort(by=ConnSortBy.Host, order=Order.Asc)

    class _H(App[None]):
        def compose(self) -> ComposeResult:
            yield ConnectionListView(populated_state, sort=sort)

    app = _H()
    async with app.run_test(size=(200, 30)) as pilot:
        await pilot.pause()
        cl = app.query_one(ConnectionListView)
        # Column 0 = host. alpha.io should come before zebra.io.
        first = str(cl.get_cell_at((0, 0)))
        second = str(cl.get_cell_at((1, 0)))
        assert "alpha" in first
        assert "zebra" in second


async def test_rule_list_sort_by_proxy_dsc(populated_state: AppState) -> None:
    sort = RuleSort(by=RuleSortBy.Proxy, order=Order.Desc)

    class _H(App[None]):
        def compose(self) -> ComposeResult:
            yield RuleListView(populated_state, sort=sort)

    app = _H()
    async with app.run_test() as pilot:
        await pilot.pause()
        rl = app.query_one(RuleListView)
        # Column 2 = proxy. Desc → ProxyB, ProxyA, DIRECT.
        first = str(rl.get_cell_at((0, 2)))
        last = str(rl.get_cell_at((2, 2)))
        assert "ProxyB" in first
        assert "DIRECT" in last
