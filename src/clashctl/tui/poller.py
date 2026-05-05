"""Background polling and streaming for the Clash controller.

The Poller runs four cooperative loops:

- **slow** — `/version`, `/configs`, `/proxies`, `/rules` (default every 5s,
  staggered evenly across the window so we never hit the controller with
  four simultaneous requests).
- **fast** — `/connections` (default every 1s).
- **traffic stream** — line-delimited JSON from `/traffic`, with exponential
  reconnect backoff on disconnect.
- **logs stream** — same shape, for `/logs`.

The Poller is plain asyncio code: no Textual imports here. It posts
`textual.message.Message` instances via the `post` callable injected by
the App. Cancellation is propagated through `asyncio.CancelledError`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from textual.message import Message

from clashctl.api import Clash, stream_logs, stream_traffic
from clashctl.api.errors import ClashError, StreamError
from clashctl.tui.messages import (
    ConfigUpdate,
    ConnectionsUpdate,
    LogUpdate,
    NetworkError,
    ProxiesUpdate,
    RulesUpdate,
    StreamReconnect,
    TrafficUpdate,
    VersionUpdate,
)

log = logging.getLogger(__name__)

PostFn = Callable[[Message], None]


class Poller:
    """Owns the four background loops; one instance per active Clash client."""

    BACKOFF_INITIAL = 1.0
    BACKOFF_MAX = 30.0
    # A stream that returns in less than this is treated as a failed
    # connection — a healthy /traffic or /logs endpoint stays open until the
    # client disconnects, so an immediate clean close is almost always
    # "wrong server / endpoint not implemented" and must trigger backoff to
    # avoid pinning the CPU.
    STREAM_HEALTHY_SECS = 2.0

    def __init__(
        self,
        clash: Clash,
        post: PostFn,
        *,
        slow_secs: float = 5.0,
        fast_secs: float = 1.0,
    ) -> None:
        self.clash = clash
        self.post = post
        self.slow_secs = slow_secs
        self.fast_secs = fast_secs

    async def run(self) -> None:
        """Run all four loops concurrently. Returns only on cancellation."""
        await asyncio.gather(
            self._slow_loop(),
            self._fast_loop(),
            self._traffic_loop(),
            self._log_loop(),
        )

    # --- one-shot fetchers ------------------------------------------------
    #
    # Each fetcher catches Exception (not just ClashError) so a single bad
    # response — network blip, schema drift, pydantic ValidationError — turns
    # into a NetworkError surface instead of tearing down the whole worker.
    # CancelledError is BaseException, so it still propagates for shutdown.

    async def fetch_version(self) -> None:
        try:
            v = await self.clash.version()
            self.post(VersionUpdate(v))
        except Exception as e:
            self.post(NetworkError("version", str(e)))

    async def fetch_configs(self) -> None:
        try:
            c = await self.clash.configs()
            self.post(ConfigUpdate(c))
        except Exception as e:
            self.post(NetworkError("configs", str(e)))

    async def fetch_proxies(self) -> None:
        try:
            p = await self.clash.proxies()
            self.post(ProxiesUpdate(p))
        except Exception as e:
            self.post(NetworkError("proxies", str(e)))

    async def fetch_rules(self) -> None:
        try:
            r = await self.clash.rules()
            self.post(RulesUpdate(r))
        except Exception as e:
            self.post(NetworkError("rules", str(e)))

    async def fetch_connections(self) -> None:
        try:
            c = await self.clash.connections()
            self.post(ConnectionsUpdate(c))
        except Exception as e:
            self.post(NetworkError("connections", str(e)))

    # --- loops ------------------------------------------------------------

    async def _slow_loop(self) -> None:
        # Run the four slow fetches concurrently so a single timeout
        # (e.g. on a wrong / slow server) doesn't serialize and drag the
        # whole cycle to 4× the timeout.
        fetchers = [
            self.fetch_version,
            self.fetch_configs,
            self.fetch_proxies,
            self.fetch_rules,
        ]
        while True:
            await asyncio.gather(*(f() for f in fetchers))
            await asyncio.sleep(self.slow_secs)

    async def _fast_loop(self) -> None:
        # Tiny initial offset so we don't fire at exactly the same moment as
        # the slow loop's first fetch.
        await asyncio.sleep(0.1)
        while True:
            await self.fetch_connections()
            await asyncio.sleep(self.fast_secs)

    async def _traffic_loop(self) -> None:
        await self._stream_loop("traffic", self._read_traffic)

    async def _log_loop(self) -> None:
        await self._stream_loop("logs", self._read_logs)

    async def _read_traffic(self) -> int:
        n = 0
        async for t in stream_traffic(self.clash):
            self.post(TrafficUpdate(t))
            n += 1
        return n

    async def _read_logs(self) -> int:
        n = 0
        async for line in stream_logs(self.clash):
            self.post(LogUpdate(line))
            n += 1
        return n

    async def _stream_loop(self, name: str, reader: Callable[[], object]) -> None:
        backoff = self.BACKOFF_INITIAL
        first = True
        loop = asyncio.get_running_loop()
        while True:
            if not first:
                self.post(StreamReconnect(name))
            first = False
            started = loop.time()
            failed = False
            try:
                await reader()  # type: ignore[misc]
            except (StreamError, ClashError) as e:
                self.post(NetworkError(name, str(e)))
                failed = True
            except Exception as e:
                # Don't let an unexpected exception (httpx, pydantic, …) tear
                # down the loop — surface it as a NetworkError and back off.
                self.post(NetworkError(name, str(e)))
                failed = True
            elapsed = loop.time() - started
            if failed or elapsed < self.STREAM_HEALTHY_SECS:
                # Either an explicit error, or a suspiciously fast clean
                # close (server doesn't actually serve this stream). Apply
                # exponential backoff so we don't busy-loop.
                await asyncio.sleep(min(backoff, self.BACKOFF_MAX))
                backoff = min(backoff * 2, self.BACKOFF_MAX)
            else:
                # The stream stayed open long enough to look healthy; reset.
                backoff = self.BACKOFF_INITIAL
