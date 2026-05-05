"""ClashCtlApp — owns the Clash client, AppState, and pollers.

The visual layout lives in `tui/screens/main.py`. The App routes poller
messages into `AppState` and tells the active screen what to refresh.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
from typing import TYPE_CHECKING, ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from clashctl_py.api import Clash
from clashctl_py.api.errors import ClashError
from clashctl_py.config import AppConfig, Server, default_config_path, load_config
from clashctl_py.state import AppState
from clashctl_py.tui.messages import (
    ApplySelectionRequest,
    ConfigUpdate,
    ConnectionsUpdate,
    LogUpdate,
    NetworkError,
    ProxiesUpdate,
    RulesUpdate,
    StreamReconnect,
    TestLatencyRequest,
    TrafficUpdate,
    VersionUpdate,
)
from clashctl_py.tui.poller import Poller
from clashctl_py.tui.screens import MainScreen, ServerSelectScreen

if TYPE_CHECKING:
    from textual.worker import Worker


class ClashCtlApp(App[None]):
    TITLE = "clashctl"

    # Hard ceiling on how long graceful shutdown is allowed to take before
    # we forcibly kill the process. Anything blocked on network I/O (slow
    # server, hung stream) gets blown away rather than wedging exit.
    _FORCE_EXIT_AFTER_SECS = 0.5

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        # ctrl+c is priority=True so it fires even when a child widget
        # (e.g. an Input field in the add-server modal) has focus.
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+s", "open_server_picker", "Server"),
    ]

    def __init__(self, app_config: AppConfig) -> None:
        super().__init__()
        self.app_config = app_config
        self.state = AppState(
            traffic_maxlen=app_config.ui.traffic_history,
            log_maxlen=app_config.ui.log_buffer,
        )
        self.clash: Clash | None = None
        self._poller_worker: Worker[None] | None = None
        self._main_screen: MainScreen | None = None

    async def on_mount(self) -> None:
        self._main_screen = MainScreen(self.state)
        await self.push_screen(self._main_screen)

        server = self.app_config.using_server()
        if server is None:
            self._open_picker(initial=True)
            return
        await self._connect_to(server)

    # --- server picker (Ctrl+S) ------------------------------------------

    def action_open_server_picker(self) -> None:
        # Don't stack pickers on top of each other.
        if isinstance(self.screen, ServerSelectScreen):
            return
        self._open_picker(initial=False)

    def _open_picker(self, *, initial: bool) -> None:
        def _on_picked(result: Server | None) -> None:
            if result is None:
                if initial:
                    # First-run with nothing selected: nothing to do.
                    self.exit(message="No server selected.")
                return
            # The modal already saved the config to disk. Reload to pick up
            # any add/delete operations that happened during the modal flow.
            self.app_config = load_config(default_config_path())
            self.run_worker(
                self.swap_server(result),
                group="connect",
                exclusive=True,
                description="server_swap",
            )

        self.push_screen(ServerSelectScreen(self.app_config), _on_picked)

    # --- connection management --------------------------------------------

    async def _connect_to(self, server: Server) -> None:
        self.clash = Clash(
            server.url,
            secret=server.secret,
            timeout_ms=self.app_config.ui.test_timeout_ms,
        )
        self.title = f"clashctl — {server.name or server.url}"
        self._start_pollers()
        self._refresh_status()

    def _start_pollers(self) -> None:
        assert self.clash is not None
        poller = Poller(
            self.clash,
            self.post_message,
            slow_secs=self.app_config.ui.refresh_slow_secs,
            fast_secs=self.app_config.ui.refresh_fast_secs,
        )
        self._poller_worker = self.run_worker(
            poller.run(),
            group="net",
            exclusive=False,
            description="poller",
        )

    async def swap_server(self, server: Server) -> None:
        if self._poller_worker is not None:
            self._poller_worker.cancel()
            self._poller_worker = None
        if self.clash is not None:
            await self.clash.aclose()
            self.clash = None
        self.state.reset_for_new_server()
        if self._main_screen is not None:
            self._main_screen.replay_logs()
            self._main_screen.refresh_status()
            self._main_screen.refresh_proxies()
            self._main_screen.refresh_rules()
            self._main_screen.refresh_connections()
        await self._connect_to(server)

    async def on_unmount(self) -> None:
        if self.clash is not None:
            await self.clash.aclose()

    # --- quit -----------------------------------------------------------
    #
    # We want q / ctrl+c to exit *immediately*, even when the poller is
    # mid-fetch on a slow server or a stream is hung. Strategy:
    # 1. Schedule a hard `os._exit` from a daemon thread as a deadline.
    #    If anything in the graceful path blocks for too long, this fires
    #    and tears the process down regardless.
    # 2. Cancel the poller worker so it stops issuing requests.
    # 3. Close the HTTP client with a tight timeout, aborting in-flight
    #    requests so the awaits inside the poller can unwind quickly.
    # 4. Hand off to Textual's normal `exit()` path.

    async def action_quit(self) -> None:
        self._arm_force_exit()
        if self._poller_worker is not None:
            self._poller_worker.cancel()
            self._poller_worker = None
        if self.clash is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.clash.aclose(), timeout=0.2)
            self.clash = None
        self.exit()

    def _arm_force_exit(self) -> None:
        def _force_exit() -> None:
            # Best-effort terminal restore so the user's shell isn't left
            # in alt-screen / raw mode after a hard exit.
            with contextlib.suppress(Exception):
                self._driver.stop_application_mode()  # type: ignore[union-attr]
            os._exit(0)

        timer = threading.Timer(self._FORCE_EXIT_AFTER_SECS, _force_exit)
        timer.daemon = True
        timer.start()

    # --- message handlers --------------------------------------------------

    def on_version_update(self, message: VersionUpdate) -> None:
        self.state.apply_version(message.version)
        self._refresh_status()

    def on_config_update(self, message: ConfigUpdate) -> None:
        self.state.apply_config(message.config)
        self._refresh_status()

    def on_proxies_update(self, message: ProxiesUpdate) -> None:
        self.state.apply_proxies(message.proxies)
        # Status panel cares about proxy count.
        self._refresh_status()
        if self._main_screen is not None:
            self._main_screen.refresh_proxies()

    def on_rules_update(self, message: RulesUpdate) -> None:
        self.state.apply_rules(message.rules)
        if self._main_screen is not None:
            self._main_screen.refresh_rules()

    def on_connections_update(self, message: ConnectionsUpdate) -> None:
        self.state.apply_connections(message.connections)
        self._refresh_status()
        if self._main_screen is not None:
            self._main_screen.refresh_connections()

    def on_traffic_update(self, message: TrafficUpdate) -> None:
        self.state.apply_traffic(message.traffic)
        self._refresh_status()

    def on_log_update(self, message: LogUpdate) -> None:
        self.state.apply_log(message.line)
        if self._main_screen is not None:
            self._main_screen.append_log(message.line)

    def on_network_error(self, message: NetworkError) -> None:
        self.state.record_error(message.source, message.detail)
        self._refresh_status()

    def on_stream_reconnect(self, message: StreamReconnect) -> None:
        self.state.clear_error()
        self._refresh_status()

    # --- proxy actions (bubbled up from ProxyTreeView) -------------------

    def on_test_latency_request(self, message: TestLatencyRequest) -> None:
        if self.clash is None:
            return
        if self.state.testing_group is not None:
            return  # already testing — ignore re-trigger
        self.run_worker(
            self._test_group_latency(message.group),
            group="proxy_action",
            exclusive=False,
            description="latency_test",
        )

    def on_apply_selection_request(self, message: ApplySelectionRequest) -> None:
        if self.clash is None:
            return
        self.run_worker(
            self._apply_selection(message.group, message.proxy),
            group="proxy_action",
            exclusive=False,
            description="apply_selection",
        )

    async def _test_group_latency(self, group_name: str) -> None:
        assert self.clash is not None
        proxies = self.state.proxies
        if proxies is None:
            return
        group = proxies.get(group_name)
        if group is None or group.all is None:
            return

        self.state.testing_group = group_name
        if self._main_screen is not None:
            self._main_screen.refresh_proxies()

        test_url = self.app_config.ui.test_url
        timeout_ms = self.app_config.ui.test_timeout_ms
        sem = asyncio.Semaphore(8)

        async def _one(name: str) -> None:
            assert self.clash is not None
            member = self.state.proxies.get(name) if self.state.proxies else None
            if member is None or not member.proxy_type.is_normal():
                return
            async with sem:
                # Failure surfaces as delay=0 in the next /proxies refresh.
                with contextlib.suppress(ClashError):
                    await self.clash.delay(name, test_url, timeout_ms)

        try:
            await asyncio.gather(*(_one(n) for n in group.all))
            # Re-fetch /proxies so updated history shows up.
            try:
                fresh = await self.clash.proxies()
                self.post_message(ProxiesUpdate(fresh))
            except ClashError as e:
                self.post_message(NetworkError("proxies", str(e)))
        finally:
            self.state.testing_group = None
            if self._main_screen is not None:
                self._main_screen.refresh_proxies()

    async def _apply_selection(self, group: str, proxy: str) -> None:
        assert self.clash is not None
        try:
            await self.clash.select(group, proxy)
        except ClashError as e:
            self.post_message(NetworkError("select", str(e)))
            return
        try:
            fresh = await self.clash.proxies()
            self.post_message(ProxiesUpdate(fresh))
        except ClashError as e:
            self.post_message(NetworkError("proxies", str(e)))

    # --- helpers ---------------------------------------------------------

    def _refresh_status(self) -> None:
        if self._main_screen is not None:
            self._main_screen.refresh_status()
