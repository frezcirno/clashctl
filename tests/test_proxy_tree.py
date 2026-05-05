"""Phase 6 tests: ProxyTreeView mounting, ordering, and request bubbling."""

from __future__ import annotations

import asyncio

import pytest
from textual.app import App, ComposeResult

from clashctl_py.models import Proxies
from clashctl_py.state import AppState
from clashctl_py.tui.messages import ApplySelectionRequest, TestLatencyRequest
from clashctl_py.tui.widgets import ProxyTreeView
from clashctl_py.tui.widgets.proxy_tree import _GroupTag, _MemberTag

# --- fixtures ------------------------------------------------------------


def _make_proxies(*, urltest: bool = True) -> Proxies:
    """Build a small proxy graph: GLOBAL → [Auto, Manual, DIRECT].

    `Auto` is a URLTest (read-only), `Manual` is a Selector (writable).
    """
    base = {
        "DIRECT": {"type": "Direct", "history": []},
        "REJECT": {"type": "Reject", "history": []},
        "JP-1": {
            "type": "Vmess",
            "history": [{"time": "2024-01-01T00:00:00Z", "delay": 142}],
        },
        "US-1": {
            "type": "Shadowsocks",
            "history": [{"time": "2024-01-01T00:00:00Z", "delay": 0}],
        },
        "Manual": {
            "type": "Selector",
            "history": [],
            "all": ["JP-1", "US-1", "DIRECT"],
            "now": "JP-1",
        },
        "GLOBAL": {
            "type": "Selector",
            "history": [],
            "all": ["Manual", "JP-1", "US-1"],
            "now": "Manual",
        },
    }
    if urltest:
        base["Auto"] = {
            "type": "URLTest",
            "history": [],
            "all": ["JP-1", "US-1"],
            "now": "JP-1",
        }
    return Proxies.model_validate(base)


@pytest.fixture
def state_with_proxies() -> AppState:
    s = AppState()
    s.apply_proxies(_make_proxies())
    return s


class _Harness(App[None]):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        yield ProxyTreeView(self._state)


# --- mounting + population ----------------------------------------------


async def test_proxy_tree_mounts_with_groups(state_with_proxies: AppState) -> None:
    app = _Harness(state_with_proxies)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        group_names = {
            n.data.name for n in tree.root.children if isinstance(n.data, _GroupTag)
        }
        # Built-ins (DIRECT/REJECT) are not groups; raw proxies (JP-1) aren't either.
        assert group_names == {"GLOBAL", "Auto", "Manual"}


async def test_proxy_tree_expands_to_show_members(state_with_proxies: AppState) -> None:
    app = _Harness(state_with_proxies)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        manual = next(
            n
            for n in tree.root.children
            if isinstance(n.data, _GroupTag) and n.data.name == "Manual"
        )
        manual.expand()
        await pilot.pause()
        member_names = {
            c.data.name for c in manual.children if isinstance(c.data, _MemberTag)
        }
        assert member_names == {"JP-1", "US-1", "DIRECT"}


async def test_groups_ordered_by_rule_frequency() -> None:
    """Groups referenced more often in rules come first."""
    s = AppState()
    s.apply_proxies(_make_proxies())
    # Manually set rule_frequency (normally set by apply_rules).
    s.rule_frequency = {"Auto": 10, "GLOBAL": 3}

    app = _Harness(s)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        order = [
            n.data.name for n in tree.root.children if isinstance(n.data, _GroupTag)
        ]
        # Auto (10) before GLOBAL (3) before Manual (no freq → alphabetical at end).
        assert order.index("Auto") < order.index("GLOBAL")
        assert order.index("GLOBAL") < order.index("Manual")


# --- members sort -------------------------------------------------------


async def test_members_default_sort_is_delay_asc() -> None:
    """Within a group, members default-sort by delay ascending; 0/None go last."""
    s = AppState()
    s.apply_proxies(
        Proxies.model_validate(
            {
                "G": {
                    "type": "Selector",
                    "history": [],
                    "all": ["fast", "slow", "broken", "untested"],
                    "now": "fast",
                },
                "fast": {
                    "type": "Vmess",
                    "history": [{"time": "2024-01-01T00:00:00Z", "delay": 50}],
                },
                "slow": {
                    "type": "Vmess",
                    "history": [{"time": "2024-01-01T00:00:00Z", "delay": 250}],
                },
                "broken": {
                    "type": "Vmess",
                    "history": [{"time": "2024-01-01T00:00:00Z", "delay": 0}],
                },
                "untested": {"type": "Vmess", "history": []},
            }
        )
    )
    app = _Harness(s)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        grp = tree.root.children[0]
        grp.expand()
        await pilot.pause()
        names = [
            c.data.name for c in grp.children if isinstance(c.data, _MemberTag)
        ]
        assert names == ["fast", "slow", "broken", "untested"]


# --- bindings --------------------------------------------------------


async def test_t_on_group_posts_test_request(state_with_proxies: AppState) -> None:
    posted: list[str] = []

    class _Capture(_Harness):
        def on_test_latency_request(self, msg: TestLatencyRequest) -> None:
            posted.append(msg.group)

    app = _Capture(state_with_proxies)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        tree.focus()
        await pilot.pause()
        # Cursor lands on first group by default.
        await pilot.press("t")
        await pilot.pause(0.05)
        assert len(posted) == 1


async def test_enter_on_selector_member_posts_apply(
    state_with_proxies: AppState,
) -> None:
    posted: list[tuple[str, str]] = []

    class _Capture(_Harness):
        def on_apply_selection_request(self, msg: ApplySelectionRequest) -> None:
            posted.append((msg.group, msg.proxy))

    app = _Capture(state_with_proxies)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        tree.focus()
        # Find the Manual group node + its first child; select it directly.
        manual = next(
            n
            for n in tree.root.children
            if isinstance(n.data, _GroupTag) and n.data.name == "Manual"
        )
        manual.expand()
        await pilot.pause()
        first_member = manual.children[0]
        # Simulate pressing Enter on a member
        tree.select_node(first_member)
        await pilot.pause(0.05)
        assert len(posted) == 1
        group, proxy = posted[0]
        assert group == "Manual"
        assert proxy in {"JP-1", "US-1", "DIRECT"}


async def test_enter_on_urltest_member_does_nothing(
    state_with_proxies: AppState,
) -> None:
    """URLTest groups are read-only; Enter on a member should not post."""
    posted: list[tuple[str, str]] = []

    class _Capture(_Harness):
        def on_apply_selection_request(self, msg: ApplySelectionRequest) -> None:
            posted.append((msg.group, msg.proxy))

    app = _Capture(state_with_proxies)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        auto = next(
            n
            for n in tree.root.children
            if isinstance(n.data, _GroupTag) and n.data.name == "Auto"
        )
        auto.expand()
        await pilot.pause()
        tree.select_node(auto.children[0])
        await pilot.pause(0.05)
        assert posted == []


async def test_sort_cycle_via_s(state_with_proxies: AppState) -> None:
    app = _Harness(state_with_proxies)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        tree.focus()
        await pilot.pause()
        start = (tree._sort.by, tree._sort.order)
        for _ in range(6):
            await pilot.press("s")
            await pilot.pause(0.02)
        assert (tree._sort.by, tree._sort.order) == start


# --- testing indicator -----------------------------------------------


async def test_testing_class_set_when_testing_group(
    state_with_proxies: AppState,
) -> None:
    state_with_proxies.testing_group = "Manual"
    app = _Harness(state_with_proxies)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.has_class("testing")


async def test_refresh_preserves_expansion(state_with_proxies: AppState) -> None:
    app = _Harness(state_with_proxies)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        manual = next(
            n
            for n in tree.root.children
            if isinstance(n.data, _GroupTag) and n.data.name == "Manual"
        )
        manual.expand()
        await pilot.pause()
        # Refresh — expansion should survive.
        tree.refresh_content()
        await pilot.pause()
        manual_again = next(
            n
            for n in tree.root.children
            if isinstance(n.data, _GroupTag) and n.data.name == "Manual"
        )
        assert manual_again.is_expanded


# --- empty state ----------------------------------------------------


async def test_empty_state_renders_without_crashing() -> None:
    app = _Harness(AppState())
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ProxyTreeView)
        assert tree.root is not None
        assert len(tree.root.children) == 0


# --- async correctness sanity --------------------------------------


def test_module_imports_in_no_event_loop() -> None:
    """Importing should not require an event loop (sync-friendly)."""
    # If anything top-level invoked asyncio.get_event_loop, this would raise.
    asyncio.new_event_loop().close()
    from clashctl_py.tui.widgets import proxy_tree as pt  # noqa: F401
