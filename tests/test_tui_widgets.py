"""Smoke-level tests for the Phase 4 widgets via Textual's run_test().

These verify mounting + state plumbing — not pixel-precise output. Visual
regressions can be added with pytest-textual-snapshot in later phases if
needed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult

from clashctl.models import (
    Connection,
    Connections,
    LogLevel,
    LogLine,
    Metadata,
    RuleType,
    Traffic,
    Version,
)
from clashctl.state import AppState
from clashctl.tui.widgets import LogView, StatusPanel
from clashctl.tui.widgets.status_panel import StatusCharts, StatusInfo


def _conn(cid: str, upload: int = 0, download: int = 0) -> Connection:
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
            host="x.com",
            network="tcp",
        ),
        rule=RuleType.Match,
        rule_payload="",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        chains=[],
    )


# --- StatusPanel ----------------------------------------------------------


@pytest.fixture
def populated_state() -> AppState:
    s = AppState()
    s.apply_version(Version(version="v1.18.0", premium=False))
    s.apply_traffic(Traffic(up=1024, down=2048))
    s.apply_traffic(Traffic(up=2048, down=4096))
    s.apply_connections(
        Connections(
            connections=[_conn("a", upload=10, download=20)],
            uploadTotal=1_000_000,
            downloadTotal=5_000_000,
        )
    )
    return s


class _StatusHarness(App[None]):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        yield StatusPanel(self._state)


async def test_status_panel_mounts(populated_state: AppState) -> None:
    app = _StatusHarness(populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        info = app.query_one(StatusInfo)
        charts = app.query_one(StatusCharts)
        assert info is not None
        assert charts is not None


async def test_status_panel_refresh_updates_sparkline(
    populated_state: AppState,
) -> None:
    app = _StatusHarness(populated_state)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Sparkline

        # Trigger a refresh after the App has finished mounting.
        app.query_one(StatusPanel).refresh_content()
        await pilot.pause()
        up_chart = app.query_one("#up_chart", Sparkline)
        down_chart = app.query_one("#down_chart", Sparkline)
        assert list(up_chart.data or []) == [1024.0, 2048.0]
        assert list(down_chart.data or []) == [2048.0, 4096.0]


async def test_status_panel_handles_empty_state() -> None:
    """No traffic / no version should still render without crashing."""
    app = _StatusHarness(AppState())
    async with app.run_test() as pilot:
        await pilot.pause()
        # Still mounted, no exceptions.
        assert app.query_one(StatusInfo) is not None


# --- LogView -------------------------------------------------------------


class _LogHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield LogView()


async def test_log_view_appends_lines() -> None:
    app = _LogHarness()
    async with app.run_test() as pilot:
        await pilot.pause()
        lv = app.query_one(LogView)
        lv.append_line(LogLine(type=LogLevel.Info, payload="hello"))
        lv.append_line(LogLine(type=LogLevel.Error, payload="boom"))
        await pilot.pause()
        # RichLog stores lines in `.lines` (list[Strip])
        assert len(lv.lines) == 2


async def test_log_view_replay_clears_then_fills() -> None:
    app = _LogHarness()
    async with app.run_test() as pilot:
        await pilot.pause()
        lv = app.query_one(LogView)
        lv.append_line(LogLine(type=LogLevel.Info, payload="first"))
        await pilot.pause()
        assert len(lv.lines) == 1
        lv.replay(
            [
                LogLine(type=LogLevel.Warning, payload="a"),
                LogLine(type=LogLevel.Warning, payload="b"),
                LogLine(type=LogLevel.Warning, payload="c"),
            ]
        )
        await pilot.pause()
        assert len(lv.lines) == 3
