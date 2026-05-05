"""Base DataTable with sort cycling and HOLD-mode behavior.

Two modes mirror the Rust implementation:

- **NORMAL**: every refresh repopulates rows and the table auto-scrolls so
  the freshest rows stay visible.
- **HOLD** (toggled with `space`, exited with `escape`): the user's
  cursor row is preserved across refreshes by RowKey when possible; the
  viewport doesn't auto-scroll.

Sort cycling:

- `s` advances to the next (by, order) pair.
- `shift+s` (rendered as `S`) goes backwards.

Subclasses provide:

- `_columns()` — list of `(label, width_hint)` tuples
- `_iter_rows(state)` — yields `(row_key, [cells...])` tuples in display order
- `_sort` — the `RuleSort` / `ConnSort` cursor; `next()`/`prev()` mutate it
- `_sort_label_for(by)` — a short human label for the active sort key
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, ClassVar

from rich.text import Text
from textual.binding import Binding, BindingType
from textual.reactive import reactive
from textual.widgets import DataTable

if TYPE_CHECKING:
    from clashctl.state import AppState


class MovableTable(DataTable):  # type: ignore[type-arg]
    """DataTable subclass with NORMAL/HOLD modes and sort cycling."""

    DEFAULT_CSS = """
    MovableTable {
        height: 1fr;
    }
    MovableTable.hold {
        border-left: tall $accent;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_hold", "Toggle Hold"),
        Binding("escape", "exit_hold", "Exit Hold", show=False),
        Binding("s", "next_sort", "Sort →"),
        Binding("shift+s", "prev_sort", "Sort ←"),
    ]

    hold = reactive(False)

    def __init__(self, state: AppState) -> None:
        super().__init__(zebra_stripes=True, cursor_type="row", header_height=1)
        self._state = state
        self._dirty = True

    def on_mount(self) -> None:
        for label, width in self._columns():
            self.add_column(label, width=width)
        self.refresh_content()

    # --- subclass contract ------------------------------------------------

    @abstractmethod
    def _columns(self) -> list[tuple[str, int | None]]: ...

    @abstractmethod
    def _iter_rows(self, state: AppState) -> Iterable[tuple[Any, list[Text | str]]]: ...

    def _by_for_column(self, col_index: int) -> Any | None:
        """Map a column index to its sort `by` enum (or None if not sortable).

        Default returns None for every column (no header-click sorting).
        Subclasses override to enable click-to-sort.
        """
        return None

    def _cycle_sort_by(self, by: Any) -> None:
        """Advance `self._sort` for header-click cycling. Default delegates to the
        sort cursor's `cycle_by` method if present."""
        sort = getattr(self, "_sort", None)
        cycle = getattr(sort, "cycle_by", None)
        if cycle is not None:
            cycle(by)

    # --- public refresh entry --------------------------------------------

    def refresh_content(self) -> None:
        """Repopulate rows from `self._state`. Preserves the cursor's position
        (by row key, falling back to row index) and horizontal scroll across
        refreshes."""
        # Capture cursor state before clearing.
        prior_row = self.cursor_row
        prior_key = None
        if self.row_count > 0:
            try:
                prior_key = self.coordinate_to_cell_key((prior_row, 0)).row_key
            except Exception:
                prior_key = None

        # `DataTable.clear()` resets scroll_x to 0 and cursor_coordinate to
        # (0, 0); capture them so we can restore.
        prior_scroll_x = self.scroll_x

        # `clear()` is fast even at thousands of rows.
        self.clear()
        new_keys: list[Any] = []
        for key, cells in self._iter_rows(self._state):
            self.add_row(*cells, key=str(key))
            new_keys.append(key)

        if not new_keys:
            return

        # Resolve target cursor row: prefer following the prior row by key,
        # otherwise stay on the same index (clamped). This avoids the cursor
        # jumping to the first or last row whenever the data set changes.
        target_row = -1
        if prior_key is not None:
            for i, k in enumerate(new_keys):
                if str(k) == str(prior_key):
                    target_row = i
                    break
        if target_row < 0:
            target_row = min(prior_row, len(new_keys) - 1)

        if self.hold:
            # HOLD: cursor follows the prior row; let move_cursor handle vertical
            # scroll so the cursor stays visible. Restore horizontal scroll.
            self.move_cursor(row=target_row, animate=False)
            self.scroll_to(x=prior_scroll_x, animate=False)
        else:
            # NORMAL: only auto-snap the viewport to the newest row when the
            # user wasn't actively browsing (cursor was at row 0). Otherwise
            # follow the cursor so it stays where the user put it.
            self.move_cursor(row=target_row, animate=False)
            if target_row == 0:
                self.scroll_to(x=prior_scroll_x, y=0, animate=False)
            else:
                self.scroll_to(x=prior_scroll_x, animate=False)

    # --- bindings --------------------------------------------------------

    def watch_hold(self, hold: bool) -> None:
        self.set_class(hold, "hold")

    def action_toggle_hold(self) -> None:
        self.hold = not self.hold

    def action_exit_hold(self) -> None:
        self.hold = False

    def action_next_sort(self) -> None:
        self._sort_next()
        self.refresh_content()

    def action_prev_sort(self) -> None:
        self._sort_prev()
        self.refresh_content()

    @abstractmethod
    def _sort_next(self) -> None: ...

    @abstractmethod
    def _sort_prev(self) -> None: ...

    # --- header-click sorting --------------------------------------------

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Click a column header to cycle sort: asc → desc → off → asc."""
        by = self._by_for_column(event.column_index)
        if by is None:
            return
        self._cycle_sort_by(by)
        self._refresh_headers()
        self.refresh_content()
        event.stop()

    def _refresh_headers(self) -> None:
        """Rewrite column labels from `_columns()` without rebuilding the table."""
        for col, (label, _) in zip(self.columns.values(), self._columns(), strict=True):
            col.label = Text.from_markup(label)
        self.refresh()
