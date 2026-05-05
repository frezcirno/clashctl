"""Phase 7 tests: ServerSelectScreen + ServerAddScreen via run_test()."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest
from textual.app import App
from textual.binding import Binding, BindingType
from textual.widgets import Input, ListView, Static

from clashctl.config import AppConfig, Server, load_config
from clashctl.models import Version
from clashctl.tui.screens import ServerAddScreen, ServerSelectScreen

# --- helpers -------------------------------------------------------------


def _config_with(*servers: Server, using: str | None = None) -> AppConfig:
    cfg = AppConfig()
    for s in servers:
        cfg.add_server(s)
    if using is not None:
        cfg.use(using)
    return cfg


def _static_text(widget: Static) -> str:
    """Read back the plain-text content of a Static for assertions."""
    return str(widget.content)


@pytest.fixture
def tmp_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "config.toml"
    monkeypatch.setenv("CLASHCTL_CONFIG_PATH", str(p))
    return p


class _OpenPicker(App[None]):
    """Tiny App harness that pushes a ServerSelectScreen on mount."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("ctrl+c", "quit", show=False)]

    def __init__(self, app_config: AppConfig) -> None:
        super().__init__()
        self._cfg = app_config
        self.picked: Server | None = None

    async def on_mount(self) -> None:
        def _cb(result: Server | None) -> None:
            self.picked = result

        await self.push_screen(ServerSelectScreen(self._cfg), _cb)


class _OpenAdd(App[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("ctrl+c", "quit", show=False)]

    def __init__(self, app_config: AppConfig) -> None:
        super().__init__()
        self._cfg = app_config
        self.added: Server | None = None

    async def on_mount(self) -> None:
        def _cb(result: Server | None) -> None:
            self.added = result

        await self.push_screen(ServerAddScreen(self._cfg), _cb)


# --- ServerSelectScreen --------------------------------------------------


async def test_select_screen_lists_configured_servers() -> None:
    cfg = _config_with(
        Server(name="local", url="http://127.0.0.1:9090"),
        Server(name="remote", url="http://r.example:9091"),
        using="http://127.0.0.1:9090",
    )
    app = _OpenPicker(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        lv = app.screen.query_one(ListView)
        assert len(lv.children) == 2


async def test_select_screen_shows_empty_message() -> None:
    cfg = AppConfig()
    app = _OpenPicker(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        # The empty placeholder Static is rendered (no ListView when servers
        # are empty).
        assert app.screen.query("#empty")
        assert not app.screen.query(ListView)


async def test_use_dismisses_with_selected_server(tmp_config_path: Path) -> None:
    cfg = _config_with(
        Server(name="a", url="http://a.local:9090"),
        Server(name="b", url="http://b.local:9090"),
    )
    app = _OpenPicker(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Force-select the first row, then invoke the action directly so we
        # don't depend on which widget happens to hold focus.
        screen = app.screen
        assert isinstance(screen, ServerSelectScreen)
        screen.query_one(ListView).index = 0
        screen.action_use()
        await pilot.pause(0.1)
    assert app.picked is not None
    assert app.picked.url == "http://a.local:9090"
    saved = load_config(tmp_config_path)
    assert saved.using == "http://a.local:9090"


async def test_delete_removes_server_and_persists(tmp_config_path: Path) -> None:
    cfg = _config_with(
        Server(name="a", url="http://a.local:9090"),
        Server(name="b", url="http://b.local:9090"),
        using="http://a.local:9090",
    )
    app = _OpenPicker(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ServerSelectScreen)
        screen.query_one(ListView).index = 0
        screen.action_delete()
        await pilot.pause(0.1)
    saved = load_config(tmp_config_path)
    assert len(saved.servers) == 1
    assert saved.servers[0].url == "http://b.local:9090"
    # `using` was on the deleted server -> falls back to the next one.
    assert saved.using == "http://b.local:9090"


async def test_cancel_dismisses_with_none() -> None:
    cfg = _config_with(Server(name="a", url="http://a.local:9090"))
    app = _OpenPicker(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ServerSelectScreen)
        screen.action_cancel()
        await pilot.pause(0.1)
    assert app.picked is None


# --- ServerAddScreen -----------------------------------------------------


async def test_add_screen_mounts_with_empty_inputs() -> None:
    cfg = AppConfig()
    app = _OpenAdd(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#name", Input).value == ""
        assert app.screen.query_one("#url", Input).value == ""
        assert app.screen.query_one("#secret", Input).value == ""


async def test_add_screen_rejects_missing_name() -> None:
    cfg = AppConfig()
    app = _OpenAdd(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#url", Input).value = "http://x:9090"
        await pilot.pause(0.05)
        await pilot.click("#save")
        await pilot.pause(0.1)
        status = _static_text(app.screen.query_one("#status", Static))
        assert "Name" in status or "name" in status
    assert app.added is None


async def test_add_screen_rejects_invalid_url() -> None:
    cfg = AppConfig()
    app = _OpenAdd(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#name", Input).value = "x"
        app.screen.query_one("#url", Input).value = "not-a-url"
        await pilot.pause(0.05)
        await pilot.click("#save")
        await pilot.pause(0.1)
        status = _static_text(app.screen.query_one("#status", Static))
        assert "Invalid" in status
    assert app.added is None


async def test_add_screen_rejects_duplicate_url() -> None:
    cfg = _config_with(Server(name="a", url="http://x:9090"))
    app = _OpenAdd(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#name", Input).value = "dup"
        app.screen.query_one("#url", Input).value = "http://x:9090"
        await pilot.pause(0.05)
        await pilot.click("#save")
        await pilot.pause(0.1)
        status = _static_text(app.screen.query_one("#status", Static))
        assert "exists" in status.lower()
    assert app.added is None


async def test_add_screen_cancel_button() -> None:
    cfg = AppConfig()
    app = _OpenAdd(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#cancel")
        await pilot.pause(0.1)
    assert app.added is None


async def test_add_screen_probe_success_dismisses_with_server() -> None:
    """Mock the Clash probe to succeed; the screen should dismiss."""
    cfg = AppConfig()

    class _FakeClash:
        def __init__(self, *_a, **_kw): ...
        async def version(self) -> Version:
            return Version(version="v1.18.0", premium=False)

        async def aclose(self) -> None: ...

    app = _OpenAdd(cfg)
    with patch("clashctl.tui.screens.server_select.Clash", _FakeClash):
        async with app.run_test() as pilot:
            await pilot.pause()
            app.screen.query_one("#name", Input).value = "good"
            app.screen.query_one("#url", Input).value = "http://good.local:9090"
            await pilot.pause(0.05)
            await pilot.click("#save")
            await pilot.pause(0.3)
    assert app.added is not None
    assert app.added.name == "good"
    assert app.added.url == "http://good.local:9090"
    assert app.added.secret is None


async def test_add_screen_probe_failure_keeps_screen_open() -> None:
    """When probe raises, the screen should not dismiss."""
    cfg = AppConfig()

    class _FailingClash:
        def __init__(self, *_a, **_kw): ...
        async def version(self) -> Version:
            from clashctl.api.errors import ClashError

            raise ClashError("connection refused")

        async def aclose(self) -> None: ...

    app = _OpenAdd(cfg)
    with patch("clashctl.tui.screens.server_select.Clash", _FailingClash):
        async with app.run_test() as pilot:
            await pilot.pause()
            app.screen.query_one("#name", Input).value = "bad"
            app.screen.query_one("#url", Input).value = "http://bad.local:9090"
            await pilot.pause(0.05)
            await pilot.click("#save")
            await pilot.pause(0.3)
            status = _static_text(app.screen.query_one("#status", Static))
            assert "Probe failed" in status
    assert app.added is None


async def test_add_screen_secret_is_password_field() -> None:
    cfg = AppConfig()
    app = _OpenAdd(cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        secret_input = app.screen.query_one("#secret", Input)
        assert secret_input.password is True
