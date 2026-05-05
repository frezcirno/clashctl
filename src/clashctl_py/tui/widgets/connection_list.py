"""Connections tab — sortable DataTable of active connections with speeds."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from rich.text import Text

from clashctl_py.state import ConnSort, ConnSortBy
from clashctl_py.state.sort import Order
from clashctl_py.tui.widgets.movable_table import MovableTable
from clashctl_py.utils.bytesize import humanize_bytes, humanize_rate
from clashctl_py.utils.duration import humanize_since

if TYPE_CHECKING:
    from clashctl_py.state import AppState


_HEADER_FOR_BY: dict[ConnSortBy, str] = {
    ConnSortBy.Host: "Host",
    ConnSortBy.Down: "▼",
    ConnSortBy.DownSpeed: "⇊/s",
    ConnSortBy.Up: "▲",
    ConnSortBy.UpSpeed: "⇈/s",
    ConnSortBy.Time: "⏲",
    ConnSortBy.Rule: "Rule",
    ConnSortBy.Chains: "Chain",
    ConnSortBy.Type: "Type",
    ConnSortBy.Src: "Src",
    ConnSortBy.Dest: "Dst",
}


class ConnectionListView(MovableTable):
    """Live-sorted view of `AppState.connections` (ConnectionWithSpeed)."""

    _LAYOUT: list[tuple[ConnSortBy, int | None]] = [
        (ConnSortBy.Host, 32),
        (ConnSortBy.Down, 10),
        (ConnSortBy.DownSpeed, 12),
        (ConnSortBy.Up, 10),
        (ConnSortBy.UpSpeed, 12),
        (ConnSortBy.Time, 8),
        (ConnSortBy.Rule, 14),
        (ConnSortBy.Chains, 24),
        (ConnSortBy.Type, 8),
    ]

    def __init__(self, state: AppState, sort: ConnSort | None = None) -> None:
        super().__init__(state)
        self._sort = sort or ConnSort()

    def _columns(self) -> list[tuple[str, int | None]]:
        return [(self._labelled(by), w) for by, w in self._LAYOUT]

    def _by_for_column(self, col_index: int) -> ConnSortBy | None:
        if 0 <= col_index < len(self._LAYOUT):
            return self._LAYOUT[col_index][0]
        return None

    def _labelled(self, by: ConnSortBy) -> str:
        base = _HEADER_FOR_BY[by]
        if self._sort.by is by and self._sort.order is not Order.Off:
            arrow = "▲" if self._sort.order is Order.Asc else "▼"
            return f"{base} {arrow}"
        return base

    def _iter_rows(self, state: AppState) -> Iterable[tuple[Any, list[Text | str]]]:
        if not state.connections:
            return
        sorted_conns = self._sort.apply(state.connections)
        now = datetime.now(tz=UTC)
        dim = "grey50"
        for cws in sorted_conns:
            c = cws.connection
            m = c.metadata
            host = f"{m.host or m.destination_ip}:{m.destination_port}"
            yield (
                c.id,
                [
                    Text(host, style="bold"),
                    Text(humanize_bytes(c.download)),
                    Text(humanize_rate(cws.download_speed), style="cyan"),
                    Text(humanize_bytes(c.upload)),
                    Text(humanize_rate(cws.upload_speed), style="green"),
                    Text(humanize_since(c.start, now=now)),
                    Text(c.rule.value, style="yellow"),
                    Text(" → ".join(c.chains), style=dim),
                    Text(m.connection_type, style=dim),
                ],
            )

    def _sort_next(self) -> None:
        self._sort.next()
        self._refresh_headers()

    def _sort_prev(self) -> None:
        self._sort.prev()
        self._refresh_headers()
