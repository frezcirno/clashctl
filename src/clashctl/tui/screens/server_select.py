"""Server picker + add-server modal.

Two `ModalScreen`s:

- `ServerSelectScreen` lists configured servers and dispatches to add /
  delete / use actions. Dismisses with the chosen `Server` (use), or
  `None` (cancel).
- `ServerAddScreen` collects name / url / secret, probes `/version` to
  validate connectivity, then dismisses with the new `Server` on
  success or `None` on cancel.

Both modals mutate the shared `AppConfig` directly and persist via
`save_config` so the App just has to reload from disk after dismiss.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ValidationError
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Static

from clashctl.api import Clash
from clashctl.api.errors import ClashError
from clashctl.config import AppConfig, Server, save_config

# --- ServerSelectScreen --------------------------------------------------


class ServerSelectScreen(ModalScreen[Server | None]):
    """List of configured servers with Use / Add / Delete actions."""

    DEFAULT_CSS = """
    ServerSelectScreen {
        align: center middle;
    }
    ServerSelectScreen > Vertical {
        width: 70;
        max-width: 80%;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    ServerSelectScreen #title {
        color: $accent;
        text-style: bold;
        padding: 0 0 1 0;
    }
    ServerSelectScreen ListView {
        height: auto;
        max-height: 12;
        margin: 0 0 1 0;
    }
    ServerSelectScreen #empty {
        padding: 1 1;
        color: $text-muted;
    }
    ServerSelectScreen #actions {
        height: auto;
        margin: 1 0 0 0;
    }
    ServerSelectScreen #actions Button {
        margin: 0 1 0 0;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Close", show=True),
        Binding("a", "add", "Add", show=True),
        Binding("d", "delete", "Delete", show=True),
        Binding("u", "use", "Use", show=True),
        Binding("enter", "use", "Use", show=False),
    ]

    def __init__(self, app_config: AppConfig) -> None:
        super().__init__()
        self._cfg = app_config

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Servers", id="title")
            if self._cfg.servers:
                yield ListView(
                    *(ListItem(Static(self._row_label(s))) for s in self._cfg.servers),
                    id="server_list",
                )
            else:
                yield Static(
                    "No servers configured. Press [a] to add one.",
                    id="empty",
                )
            with Horizontal(id="actions"):
                yield Button("Use", id="use", variant="primary")
                yield Button("Add", id="add")
                yield Button("Delete", id="delete", variant="error")
                yield Button("Close", id="close")

    def _row_label(self, s: Server) -> Text:
        active = s.url == self._cfg.using
        marker = "★ " if active else "  "
        line = Text()
        line.append(marker, style="green" if active else "dim")
        line.append(f"{s.name:<14}  ", style="bold" if active else "")
        line.append(s.url, style="dim")
        return line

    # --- actions ---------------------------------------------------------

    @on(Button.Pressed, "#use")
    def _on_use_clicked(self) -> None:
        self.action_use()

    @on(Button.Pressed, "#add")
    def _on_add_clicked(self) -> None:
        self.action_add()

    @on(Button.Pressed, "#delete")
    def _on_delete_clicked(self) -> None:
        self.action_delete()

    @on(Button.Pressed, "#close")
    def _on_close_clicked(self) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_add(self) -> None:
        def _added(server: Server | None) -> None:
            if server is None:
                return
            try:
                self._cfg.add_server(server)
                save_config(self._cfg)
            except ValueError:
                # Duplicate URL — ignore silently; ServerAddScreen would have
                # caught most cases already.
                pass
            self.refresh(recompose=True)

        self.app.push_screen(ServerAddScreen(self._cfg), _added)

    def action_use(self) -> None:
        chosen = self._cursor_server()
        if chosen is None:
            return
        self._cfg.use(chosen.url)
        save_config(self._cfg)
        self.dismiss(chosen)

    def action_delete(self) -> None:
        chosen = self._cursor_server()
        if chosen is None:
            return
        self._cfg.remove_server(chosen.url)
        save_config(self._cfg)
        self.refresh(recompose=True)

    def _cursor_server(self) -> Server | None:
        if not self._cfg.servers:
            return None
        try:
            lv = self.query_one(ListView)
        except Exception:
            return None
        idx = lv.index
        if idx is None or idx < 0 or idx >= len(self._cfg.servers):
            return None
        return self._cfg.servers[idx]


# --- ServerAddScreen -----------------------------------------------------


class ServerAddScreen(ModalScreen[Server | None]):
    """Add a new server: validates input, then probes `/version`.

    Dismisses with the saved `Server` on success or `None` on cancel.
    Persisting to disk is the parent screen's job — we only return the
    constructed model.
    """

    DEFAULT_CSS = """
    ServerAddScreen {
        align: center middle;
    }
    ServerAddScreen > Vertical {
        width: 60;
        max-width: 80%;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    ServerAddScreen #title {
        color: $accent;
        text-style: bold;
        padding: 0 0 1 0;
    }
    ServerAddScreen Input {
        margin: 0 0 1 0;
    }
    ServerAddScreen #status {
        height: 1;
        color: $text-muted;
    }
    ServerAddScreen Horizontal {
        height: auto;
        margin: 1 0 0 0;
    }
    ServerAddScreen Button {
        margin: 0 1 0 0;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, app_config: AppConfig) -> None:
        super().__init__()
        self._cfg = app_config
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Add Server", id="title")
            yield Input(placeholder="name (e.g. local)", id="name")
            yield Input(placeholder="http://host:port", id="url")
            yield Input(
                placeholder="secret (leave empty if none)", id="secret", password=True
            )
            yield Static("", id="status")
            with Horizontal():
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    # --- button handlers ------------------------------------------------

    @on(Button.Pressed, "#save")
    async def _on_save(self) -> None:
        await self._save()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted)
    async def _on_input_submitted(self, _event: Input.Submitted) -> None:
        await self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    # --- core save flow -------------------------------------------------

    async def _save(self) -> None:
        if self._busy:
            return
        name = self.query_one("#name", Input).value.strip()
        url = self.query_one("#url", Input).value.strip()
        secret = self.query_one("#secret", Input).value.strip() or None
        status = self.query_one("#status", Static)

        if not name:
            self._set_status(status, "Name is required.", "red")
            return

        try:
            server = Server(name=name, url=url, secret=secret)
        except ValidationError as e:
            self._set_status(status, f"Invalid: {self._first_msg(e)}", "red")
            return

        if any(s.url == server.url for s in self._cfg.servers):
            self._set_status(status, "A server with this URL already exists.", "red")
            return

        self._busy = True
        self._set_status(status, "Probing /version ...", "cyan")
        ok, detail = await self._probe(server)
        self._busy = False
        if not ok:
            self._set_status(status, f"Probe failed: {detail}", "red")
            return
        self.dismiss(server)

    async def _probe(self, server: Server) -> tuple[bool, str]:
        client = Clash(server.url, secret=server.secret, timeout_ms=5000)
        try:
            version = await client.version()
        except ClashError as e:
            return False, str(e)
        except Exception as e:  # network errors not wrapped by ClashError
            return False, str(e)
        finally:
            await client.aclose()
        return True, version.version

    @staticmethod
    def _first_msg(e: ValidationError) -> str:
        try:
            return str(e.errors()[0]["msg"])
        except Exception:
            return str(e)

    @staticmethod
    def _set_status(widget: Static, msg: str, color: str) -> None:
        widget.update(Text(msg, style=color))
