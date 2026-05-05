"""Status tab — info table on the left, two stacked sparklines on the right.

Mirrors the Rust StatusPage. The widget pulls from a shared `AppState`;
the App calls `refresh_status()` on traffic / connections / version
updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Sparkline, Static

import clashctl
from clashctl.utils.bytesize import humanize_bytes, humanize_rate

CLASHCTL_VERSION = clashctl.__version__

if TYPE_CHECKING:
    from clashctl.state import AppState


class StatusInfo(Static):
    """Left-side info table. Re-renders from AppState on demand."""

    DEFAULT_CSS = """
    StatusInfo {
        width: 38;
        padding: 0 1;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def on_mount(self) -> None:
        self.refresh_content()

    def refresh_content(self) -> None:
        s = self._state
        last = s.traffic_history[-1] if s.traffic_history else None

        if s.traffic_history:
            up_sum = sum(t.up for t in s.traffic_history)
            down_sum = sum(t.down for t in s.traffic_history)
            n = len(s.traffic_history)
            up_avg = humanize_rate(up_sum / n)
            down_avg = humanize_rate(down_sum / n)
        else:
            up_avg = down_avg = "?"

        ver = s.version.version if s.version else "?"
        rows: list[tuple[str, str]] = [
            ("⇉ Connections", str(len(s.connections))),
            ("▲ Upload", humanize_rate(last.up) if last else "?"),
            ("▼ Download", humanize_rate(last.down) if last else "?"),
            ("▲ Avg.", up_avg),
            ("▼ Avg.", down_avg),
            ("▲ Max", humanize_rate(s.max_traffic.up)),
            ("▼ Max", humanize_rate(s.max_traffic.down)),
            ("▲ Total", humanize_bytes(s.connection_totals[0])),
            ("▼ Total", humanize_bytes(s.connection_totals[1])),
            ("", ""),
            ("Clash Ver.", ver),
            ("Clashctl Ver.", CLASHCTL_VERSION),
        ]

        table = Table.grid(padding=(0, 1), expand=True)
        table.add_column(justify="left", ratio=2)
        table.add_column(justify="right", ratio=3)
        for label, value in rows:
            table.add_row(Text(label, style="dim"), Text(value))

        err = s.last_error
        if err is not None:
            footer = Text(f"⚠ {err[0]}: {err[1]}", style="yellow")
            self.update(Panel(Group(table, footer), title="Info", border_style="cyan"))
        else:
            self.update(Panel(table, title="Info", border_style="cyan"))


class StatusCharts(Vertical):
    """Right-side chart pane: upload sparkline above, download below."""

    DEFAULT_CSS = """
    StatusCharts {
        height: 1fr;
        padding: 0 1;
    }
    StatusCharts > #up_label,
    StatusCharts > #down_label {
        height: 1;
        color: $text-muted;
    }
    StatusCharts > Sparkline {
        height: 1fr;
        min-height: 3;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        yield Static("▲ Upload (max ?)", id="up_label")
        yield Sparkline(
            data=[],
            id="up_chart",
            min_color="green",
            max_color="ansi_bright_green",
        )
        yield Static("▼ Download (max ?)", id="down_label")
        yield Sparkline(
            data=[],
            id="down_chart",
            min_color="cyan",
            max_color="ansi_bright_cyan",
        )

    def refresh_content(self) -> None:
        s = self._state
        up_data = [float(t.up) for t in s.traffic_history]
        down_data = [float(t.down) for t in s.traffic_history]
        self.query_one("#up_chart", Sparkline).data = up_data
        self.query_one("#down_chart", Sparkline).data = down_data
        up_max = max(up_data, default=0.0)
        down_max = max(down_data, default=0.0)
        self.query_one("#up_label", Static).update(
            Text(f"▲ Upload (max {humanize_rate(up_max)})", style="green")
        )
        self.query_one("#down_label", Static).update(
            Text(f"▼ Download (max {humanize_rate(down_max)})", style="cyan")
        )


class StatusPanel(Horizontal):
    """Status tab root. Composes info table + charts."""

    DEFAULT_CSS = """
    StatusPanel {
        height: 1fr;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        yield StatusInfo(self._state)
        yield StatusCharts(self._state)

    def refresh_content(self) -> None:
        # Children aren't queryable until compose+mount finish; tolerate the
        # race that can happen during a server swap.
        from textual.css.query import NoMatches

        try:
            self.query_one(StatusInfo).refresh_content()
            self.query_one(StatusCharts).refresh_content()
        except NoMatches:
            return
