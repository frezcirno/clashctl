"""Rules tab — sortable DataTable of `(type, payload, proxy)`."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from rich.text import Text

from clashctl.state import RuleSort, RuleSortBy
from clashctl.state.sort import Order
from clashctl.tui.theme import rule_type_color
from clashctl.tui.widgets.movable_table import MovableTable

if TYPE_CHECKING:
    from clashctl.state import AppState


_BY_LABEL: dict[RuleSortBy, str] = {
    RuleSortBy.Payload: "payload",
    RuleSortBy.Type: "type",
    RuleSortBy.Proxy: "proxy",
}


class RuleListView(MovableTable):
    """Live-sorted view of `AppState.rules`."""

    _LAYOUT: list[tuple[RuleSortBy, str, int | None]] = [
        (RuleSortBy.Type, "Type", 16),
        (RuleSortBy.Payload, "Payload", 40),
        (RuleSortBy.Proxy, "Proxy", None),
    ]

    def __init__(self, state: AppState, sort: RuleSort | None = None) -> None:
        super().__init__(state)
        self._sort = sort or RuleSort()

    def _columns(self) -> list[tuple[str, int | None]]:
        return [(self._labelled(label, by), w) for by, label, w in self._LAYOUT]

    def _by_for_column(self, col_index: int) -> RuleSortBy | None:
        if 0 <= col_index < len(self._LAYOUT):
            return self._LAYOUT[col_index][0]
        return None

    def _labelled(self, base: str, by: RuleSortBy) -> str:
        if self._sort.by is not by or self._sort.order is Order.Off:
            return base
        arrow = "▲" if self._sort.order is Order.Asc else "▼"
        return f"{base} {arrow}"

    def _iter_rows(self, state: AppState) -> Iterable[tuple[Any, list[Text | str]]]:
        if state.rules is None:
            return
        sorted_rules = self._sort.apply(state.rules.rules)
        # Use index as stable row key (rules don't have unique ids).
        for i, r in enumerate(sorted_rules):
            type_cell = Text(r.rule_type.value, style=rule_type_color(r.rule_type))
            payload = r.payload if r.payload else "*"
            payload_cell = Text(payload, style="bold")
            if r.proxy in {"DIRECT", "REJECT"}:
                proxy_cell = Text(r.proxy, style="grey50")
            else:
                proxy_cell = Text(r.proxy, style="yellow")
            yield (i, [type_cell, payload_cell, proxy_cell])

    def _sort_next(self) -> None:
        self._sort.next()
        self._refresh_headers()

    def _sort_prev(self) -> None:
        self._sort.prev()
        self._refresh_headers()
