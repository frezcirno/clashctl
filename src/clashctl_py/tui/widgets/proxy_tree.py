"""Proxies tab — collapsible tree of groups, expandable to member latency rows.

Group ordering matches the Rust version: groups referenced by rules come
first (sorted by frequency descending), then the rest alphabetically.

Bindings:
- `t` triggers a latency test of the focused group's normal members.
- `enter` on a Selector member sends a switch request to the App.
- `s` / `shift+s` cycle the member sort key.

The widget never talks to the network. It posts `TestLatencyRequest`
and `ApplySelectionRequest` messages that bubble up to the App, which
owns the Clash client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual.binding import Binding, BindingType
from textual.widgets import Tree

from clashctl_py.models import Proxy
from clashctl_py.state import Order, ProxySort, ProxySortBy
from clashctl_py.tui.messages import ApplySelectionRequest, TestLatencyRequest
from clashctl_py.tui.theme import latency_color

if TYPE_CHECKING:
    from clashctl_py.state import AppState


# --- node data tags -------------------------------------------------------


@dataclass(frozen=True)
class _GroupTag:
    name: str


@dataclass(frozen=True)
class _MemberTag:
    group: str
    name: str


_NodeTag = _GroupTag | _MemberTag


# --- widget --------------------------------------------------------------


class ProxyTreeView(Tree[_NodeTag]):
    DEFAULT_CSS = """
    ProxyTreeView {
        height: 1fr;
        padding: 0 1;
    }
    ProxyTreeView.testing {
        border-left: tall $accent;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("t", "test_latency", "Test latency"),
        Binding("s", "next_sort", "Sort →"),
        Binding("shift+s", "prev_sort", "Sort ←"),
    ]

    def __init__(self, state: AppState, sort: ProxySort | None = None) -> None:
        super().__init__("Proxies", id="proxy_tree")
        self._state = state
        self._sort = sort or ProxySort(by=ProxySortBy.Delay, order=Order.Asc)
        self.show_root = False
        self.guide_depth = 3

    def on_mount(self) -> None:
        self.refresh_content()

    # --- public refresh ---------------------------------------------------

    def refresh_content(self) -> None:
        """Rebuild the tree from `self._state`, preserving expansion + cursor."""
        expanded = self._capture_expanded()
        cursor = self._capture_cursor()
        self.clear()
        self._populate()
        self._restore(expanded, cursor)
        self.set_class(self._state.testing_group is not None, "testing")

    # --- snapshot / restore ----------------------------------------------

    def _capture_expanded(self) -> set[str]:
        out: set[str] = set()
        if self.root is None:
            return out
        for node in self.root.children:
            tag = node.data
            if isinstance(tag, _GroupTag) and node.is_expanded:
                out.add(tag.name)
        return out

    def _capture_cursor(self) -> _NodeTag | None:
        node = self.cursor_node
        if node is None or node.data is None:
            return None
        return node.data

    def _restore(self, expanded: set[str], cursor: _NodeTag | None) -> None:
        if self.root is None:
            return
        target_line: int | None = None
        for grp_node in self.root.children:
            tag = grp_node.data
            if not isinstance(tag, _GroupTag):
                continue
            if tag.name in expanded:
                grp_node.expand()
            if isinstance(cursor, _GroupTag) and cursor.name == tag.name:
                target_line = grp_node.line
            elif isinstance(cursor, _MemberTag) and cursor.group == tag.name:
                for m_node in grp_node.children:
                    if (
                        isinstance(m_node.data, _MemberTag)
                        and m_node.data.name == cursor.name
                    ):
                        target_line = m_node.line
                        break
        if target_line is not None and target_line >= 0:
            self.move_cursor_to_line(target_line)

    # --- population -------------------------------------------------------

    def _populate(self) -> None:
        if self._state.proxies is None or self.root is None:
            return
        for name in self._ordered_group_names():
            group = self._state.proxies.get(name)
            if group is None:
                continue
            grp_node = self.root.add(
                self._group_label(name, group),
                data=_GroupTag(name),
                expand=False,
                allow_expand=True,
            )
            members = self._sorted_members(group)
            for m_name, m_proxy in members:
                grp_node.add_leaf(
                    self._member_label(name, m_name, m_proxy, current=group.now),
                    data=_MemberTag(group=name, name=m_name),
                )

    def _ordered_group_names(self) -> list[str]:
        if self._state.proxies is None:
            return []
        groups = [name for name, _ in self._state.proxies.groups()]
        freq = self._state.rule_frequency

        def key(n: str) -> tuple[int, int, str]:
            f = freq.get(n)
            if f is not None:
                return (0, -f, n)
            return (1, 0, n)

        return sorted(groups, key=key)

    def _sorted_members(self, group: Proxy) -> list[tuple[str, Proxy]]:
        if group.all is None or self._state.proxies is None:
            return []
        items: list[tuple[str, Proxy]] = []
        for member_name in group.all:
            m = self._state.proxies.get(member_name)
            if m is not None:
                items.append((member_name, m))
        return self._sort.apply(items)

    # --- label rendering --------------------------------------------------

    def _group_label(self, name: str, group: Proxy) -> Text:
        n_members = len(group.all or [])
        parts = [
            Text(name, style="bold white"),
            Text(f"  {group.proxy_type.value}", style="cyan"),
            Text(f"  ({n_members})", style="dim"),
        ]
        if group.now:
            parts.append(Text(f"  → {group.now}", style="green"))
        if self._state.testing_group == name:
            parts.append(Text("  (testing…)", style="yellow"))
        return Text.assemble(*parts)

    def _member_label(
        self,
        group_name: str,
        name: str,
        proxy: Proxy,
        current: str | None,
    ) -> Text:
        is_current = name == current
        name_style = "bold green" if is_current else "white"
        parts: list[Text] = [
            Text(name, style=name_style),
            Text(f"  {proxy.proxy_type.value}", style="dim"),
        ]
        if proxy.proxy_type.is_normal():
            d = proxy.latest_delay
            color = latency_color(d)
            if d is None:
                txt = "  ?"
            elif d == 0:
                txt = "  ✕"
            else:
                txt = f"  {d}ms"
            parts.append(Text(txt, style=color))
        return Text.assemble(*parts)

    # --- bindings --------------------------------------------------------

    def action_test_latency(self) -> None:
        # Allow `t` whether the cursor is on a group or a member of one.
        # Falls back to the first group when no node is selected yet.
        target = self._resolve_target_group()
        if target is not None:
            self.post_message(TestLatencyRequest(target))

    def _resolve_target_group(self) -> str | None:
        node = self.cursor_node
        if node is not None and node.data is not None:
            if isinstance(node.data, _GroupTag):
                return node.data.name
            if isinstance(node.data, _MemberTag):
                return node.data.group
        # No usable cursor: fall back to the first group, if any.
        if self.root is None:
            return None
        for child in self.root.children:
            if isinstance(child.data, _GroupTag):
                return child.data.name
        return None

    def action_next_sort(self) -> None:
        self._sort.next()
        self.refresh_content()

    def action_prev_sort(self) -> None:
        self._sort.prev()
        self.refresh_content()

    def on_tree_node_selected(self, event: Tree.NodeSelected[_NodeTag]) -> None:
        node = event.node
        tag = node.data
        if not isinstance(tag, _MemberTag):
            return  # Group nodes: let default expand/collapse handle it.
        if self._state.proxies is None:
            return
        group = self._state.proxies.get(tag.group)
        if group is None or not group.proxy_type.is_selector():
            return  # Read-only group (URLTest etc.) — ignore selection attempt.
        self.post_message(ApplySelectionRequest(tag.group, tag.name))
        event.stop()
