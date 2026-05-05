"""Main TUI screen: 5 tabs in a TabbedContent.

All five tabs are real (Status, Proxies, Rules, Conns, Logs).

The Logs tab uses a hybrid append/replay strategy: while the tab is
hidden, RichLog has no width and `write()` produces empty strips, so we
buffer in `AppState.logs` and replay on tab activation. While the tab is
active, we append directly so updates appear live.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, Header, TabbedContent, TabPane

from clashctl_py.models import LogLine
from clashctl_py.tui.widgets import (
    ConnectionListView,
    LogView,
    ProxyTreeView,
    RuleListView,
    StatusPanel,
)

if TYPE_CHECKING:
    from clashctl_py.state import AppState


# Order matters: number-key bindings index into this list.
TAB_IDS = ("status", "proxies", "rules", "conns", "logs")


class MainScreen(Screen[None]):
    DEFAULT_CSS = """
    MainScreen TabbedContent {
        height: 1fr;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "switch_tab('status')", "Status", show=False),
        Binding("2", "switch_tab('proxies')", "Proxies", show=False),
        Binding("3", "switch_tab('rules')", "Rules", show=False),
        Binding("4", "switch_tab('conns')", "Conns", show=False),
        Binding("5", "switch_tab('logs')", "Logs", show=False),
    ]

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        # Per-tab "an update happened while you were hidden" flags. Set to
        # True from refresh_* when the tab isn't active; consumed on tab
        # activation so the user sees fresh content the moment they switch.
        self._dirty_status = False
        self._dirty_proxies = False
        self._dirty_rules = False
        self._dirty_conns = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="status"):
            with TabPane("1. Status", id="status"):
                yield StatusPanel(self._state)
            with TabPane("2. Proxies", id="proxies"):
                yield ProxyTreeView(self._state)
            with TabPane("3. Rules", id="rules"):
                yield RuleListView(self._state)
            with TabPane("4. Conns", id="conns"):
                yield ConnectionListView(self._state)
            with TabPane("5. Logs", id="logs"):
                yield LogView()
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    # --- update entry points called by App message handlers --------------
    #
    # All of these can fire during a server swap, when the screen is mounted
    # but its children may not yet be composed (e.g. behind a modal). Guard
    # with NoMatches. We also skip refresh when the widget's tab isn't
    # active — invisible Rich/Tree renders still cost CPU and can make the
    # active tab feel laggy when events stream in (e.g. on a wrong server
    # where /traffic + /logs and the slow fetchers all error in bursts).

    def refresh_status(self) -> None:
        if self._active_tab() != "status":
            self._dirty_status = True
            return
        self._dirty_status = False
        from textual.css.query import NoMatches
        with contextlib.suppress(NoMatches):
            self.query_one(StatusPanel).refresh_content()

    def refresh_proxies(self) -> None:
        if self._active_tab() != "proxies":
            self._dirty_proxies = True
            return
        self._dirty_proxies = False
        from textual.css.query import NoMatches
        with contextlib.suppress(NoMatches):
            self.query_one(ProxyTreeView).refresh_content()

    def refresh_rules(self) -> None:
        if self._active_tab() != "rules":
            self._dirty_rules = True
            return
        self._dirty_rules = False
        from textual.css.query import NoMatches
        with contextlib.suppress(NoMatches):
            self.query_one(RuleListView).refresh_content()

    def refresh_connections(self) -> None:
        if self._active_tab() != "conns":
            self._dirty_conns = True
            return
        self._dirty_conns = False
        from textual.css.query import NoMatches
        with contextlib.suppress(NoMatches):
            self.query_one(ConnectionListView).refresh_content()

    def append_log(self, line: LogLine) -> None:
        from textual.css.query import NoMatches
        if not self._logs_visible():
            return
        with contextlib.suppress(NoMatches):
            self.query_one(LogView).append_line(line)

    def replay_logs(self) -> None:
        from textual.css.query import NoMatches
        with contextlib.suppress(NoMatches):
            self.query_one(LogView).replay(list(self._state.logs))

    def _logs_visible(self) -> bool:
        return self._active_tab() == "logs"

    def _active_tab(self) -> str | None:
        try:
            return self.query_one(TabbedContent).active
        except Exception:
            return None

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        if event.pane is None:
            return
        # Catch up any updates that arrived while this tab was hidden. Go
        # through the widgets directly rather than the gated refresh_*
        # helpers because TabbedContent.active may not have flipped yet.
        from textual.css.query import NoMatches
        pane_id = event.pane.id
        try:
            if pane_id == "status" and self._dirty_status:
                self.query_one(StatusPanel).refresh_content()
                self._dirty_status = False
            elif pane_id == "proxies" and self._dirty_proxies:
                self.query_one(ProxyTreeView).refresh_content()
                self._dirty_proxies = False
            elif pane_id == "rules" and self._dirty_rules:
                self.query_one(RuleListView).refresh_content()
                self._dirty_rules = False
            elif pane_id == "conns" and self._dirty_conns:
                self.query_one(ConnectionListView).refresh_content()
                self._dirty_conns = False
            elif pane_id == "logs":
                self.replay_logs()
        except NoMatches:
            pass
        for child in event.pane.walk_children():
            if child.focusable:
                child.focus()
                break
