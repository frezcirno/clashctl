from __future__ import annotations

import asyncio
import contextlib

import httpx
import pytest
from textual.message import Message

from clashctl_py.api import Clash
from clashctl_py.tui.messages import (
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
from clashctl_py.tui.poller import Poller


def _make_client(transport: httpx.MockTransport) -> Clash:
    c = Clash("http://127.0.0.1:9090", secret="s")
    c._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url=c.base_url,
        headers={"Authorization": "Bearer s"},
        transport=transport,
    )
    c._stream_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url=c.base_url,
        headers={"Authorization": "Bearer s"},
        transport=transport,
    )
    return c


# --- one-shot fetchers ----------------------------------------------------


async def test_fetch_version_posts_message(mock_transport: httpx.MockTransport) -> None:
    c = _make_client(mock_transport)
    posted: list[Message] = []
    p = Poller(c, posted.append)
    await p.fetch_version()
    assert len(posted) == 1
    assert isinstance(posted[0], VersionUpdate)
    assert posted[0].version.version == "v1.18.0"
    await c.aclose()


async def test_fetch_proxies_posts_message(mock_transport: httpx.MockTransport) -> None:
    c = _make_client(mock_transport)
    posted: list[Message] = []
    p = Poller(c, posted.append)
    await p.fetch_proxies()
    assert isinstance(posted[0], ProxiesUpdate)
    assert "GLOBAL" in posted[0].proxies
    await c.aclose()


async def test_fetch_rules_posts_message(mock_transport: httpx.MockTransport) -> None:
    c = _make_client(mock_transport)
    posted: list[Message] = []
    p = Poller(c, posted.append)
    await p.fetch_rules()
    assert isinstance(posted[0], RulesUpdate)
    assert posted[0].rules.most_frequent_proxy() == "Manual"
    await c.aclose()


async def test_fetch_configs_posts_message(mock_transport: httpx.MockTransport) -> None:
    c = _make_client(mock_transport)
    posted: list[Message] = []
    p = Poller(c, posted.append)
    await p.fetch_configs()
    assert isinstance(posted[0], ConfigUpdate)
    assert posted[0].config.port == 7890
    await c.aclose()


async def test_fetch_connections_posts_message(mock_transport: httpx.MockTransport) -> None:
    c = _make_client(mock_transport)
    posted: list[Message] = []
    p = Poller(c, posted.append)
    await p.fetch_connections()
    assert isinstance(posted[0], ConnectionsUpdate)
    assert posted[0].connections.download_total == 12345678
    await c.aclose()


# --- error handling ------------------------------------------------------


async def test_fetcher_posts_network_error_on_5xx() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    c = _make_client(httpx.MockTransport(handler))
    posted: list[Message] = []
    p = Poller(c, posted.append)
    await p.fetch_version()
    assert len(posted) == 1
    assert isinstance(posted[0], NetworkError)
    assert posted[0].source == "version"
    await c.aclose()


async def test_fetcher_posts_network_error_on_transport_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    c = _make_client(httpx.MockTransport(handler))
    posted: list[Message] = []
    p = Poller(c, posted.append)
    await p.fetch_proxies()
    assert isinstance(posted[0], NetworkError)
    assert posted[0].source == "proxies"
    await c.aclose()


# --- streaming ----------------------------------------------------------


async def test_traffic_loop_yields_then_reconnects() -> None:
    """First call returns one line then EOF; loop should post + try to reconnect."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if request.url.path.endswith("/traffic"):
            # Always return the same body. The loop will try to reconnect.
            return httpx.Response(200, content=b'{"up": 10, "down": 20}\n')
        return httpx.Response(404)

    c = _make_client(httpx.MockTransport(handler))
    posted: list[Message] = []
    p = Poller(c, posted.append, slow_secs=999.0, fast_secs=999.0)
    p.BACKOFF_INITIAL = 0.01

    task = asyncio.create_task(p._traffic_loop())
    # Let it iterate a few times
    await asyncio.sleep(0.1)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await c.aclose()

    traffic = [m for m in posted if isinstance(m, TrafficUpdate)]
    reconnects = [m for m in posted if isinstance(m, StreamReconnect)]
    assert len(traffic) >= 2
    assert all(t.traffic.up == 10 and t.traffic.down == 20 for t in traffic)
    # Each reconnect after the first iteration → at least one StreamReconnect.
    assert len(reconnects) >= 1
    assert reconnects[0].source == "traffic"


async def test_log_loop_posts_logs() -> None:
    body = b'{"type":"info","payload":"started"}\n{"type":"warn","payload":"x"}\n'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    c = _make_client(httpx.MockTransport(handler))
    posted: list[Message] = []
    p = Poller(c, posted.append)
    p.BACKOFF_INITIAL = 0.01

    task = asyncio.create_task(p._log_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await c.aclose()

    logs = [m for m in posted if isinstance(m, LogUpdate)]
    assert len(logs) >= 2


async def test_stream_loop_backs_off_on_connect_failure() -> None:
    """Posting NetworkError per attempt and incrementing backoff."""
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="unavailable")

    c = _make_client(httpx.MockTransport(handler))
    posted: list[Message] = []
    p = Poller(c, posted.append)
    p.BACKOFF_INITIAL = 0.01
    p.BACKOFF_MAX = 0.05

    task = asyncio.create_task(p._traffic_loop())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await c.aclose()

    errors = [m for m in posted if isinstance(m, NetworkError) and m.source == "traffic"]
    assert len(errors) >= 2
    assert attempts >= 2


# --- run() smoke ---------------------------------------------------------


async def test_run_propagates_cancellation(mock_transport: httpx.MockTransport) -> None:
    """Confirm Poller.run() can be cancelled cleanly via task.cancel()."""
    c = _make_client(mock_transport)
    posted: list[Message] = []
    p = Poller(c, posted.append, slow_secs=0.05, fast_secs=0.05)
    p.BACKOFF_INITIAL = 0.01

    task = asyncio.create_task(p.run())
    await asyncio.sleep(0.15)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await c.aclose()

    # Should have seen at least version + connections updates.
    kinds = {type(m).__name__ for m in posted}
    assert "VersionUpdate" in kinds
    assert "ConnectionsUpdate" in kinds
