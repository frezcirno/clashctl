"""Logs tab — colored RichLog with append-on-update behavior."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog

from clashctl.models import LogLine
from clashctl.tui.theme import log_level_color


class LogView(RichLog):
    """Log panel. Each line is rendered with a level-specific color prefix."""

    DEFAULT_CSS = """
    LogView {
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__(
            highlight=False,
            markup=False,
            wrap=False,
            auto_scroll=True,
        )

    def append_line(self, line: LogLine) -> None:
        level_text = Text(
            f"{line.level.value.upper():<7}",
            style=f"bold {log_level_color(line.level)}",
        )
        self.write(level_text + Text(line.payload))

    def replay(self, lines: list[LogLine]) -> None:
        """Bulk-fill from buffered state (e.g. after server hot-swap)."""
        self.clear()
        for line in lines:
            self.append_line(line)
