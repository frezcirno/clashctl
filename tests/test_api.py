from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from clashctl_py.api import Clash, stream_logs, stream_traffic
from clashctl_py.api.errors import AuthError, NotFoundError
from clashctl_py.models import LogLevel, Mode, ProxyType

FIXTURES = Path(__file__).parent / "fixtures"


def _make_client(transport: httpx.MockTransport) -> Clash:
    """Build a Clash with both internal httpx clients pointed at MockTransport."""
    c = Clash("http://127.0.0.1:9090", secret="hunter2")
    # Replace the internal AsyncClient instances with mocked ones.
    c._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url=c.base_url,
        headers={"Authorization": f"Bearer {c.secret}"},
        transport=transport,
    )
    c._stream_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url=c.base_url,
        headers={"Authorization": f"Bearer {c.secret}"},
        transport=transport,
    )
    return c


@pytest.fixture
def clash(mock_transport: httpx.MockTransport) -> Clash:
    return _make_client(mock_transport)


# --- one-shot endpoints -----------------------------------------------------


async def test_version(clash: Clash) -> None:
    v = await clash.version()
    assert v.version == "v1.18.0"
    assert v.premium is True
    await clash.aclose()


async def test_configs(clash: Clash) -> None:
    c = await clash.configs()
    assert c.port == 7890
    assert c.mode is Mode.Rule
    assert c.log_level is LogLevel.Info
    await clash.aclose()


async def test_proxies(clash: Clash) -> None:
    p = await clash.proxies()
    assert p["JP-1"].proxy_type is ProxyType.Vmess
    assert {n for n, _ in p.groups()} == {"GLOBAL", "Auto", "Manual"}
    await clash.aclose()


async def test_single_proxy(clash: Clash) -> None:
    p = await clash.proxy("JP-1")
    assert p.proxy_type is ProxyType.Vmess
    assert p.latest_delay == 142
    await clash.aclose()


async def test_rules(clash: Clash) -> None:
    r = await clash.rules()
    assert r.most_frequent_proxy() == "Manual"
    await clash.aclose()


async def test_connections(clash: Clash) -> None:
    c = await clash.connections()
    assert c.download_total == 12345678
    assert c.connections[0].metadata.host == "www.google.com"
    await clash.aclose()


async def test_select(clash: Clash) -> None:
    # No exception means the PUT succeeded (mock returns 204).
    await clash.select("Manual", "JP-1")
    await clash.aclose()


async def test_delay(clash: Clash) -> None:
    d = await clash.delay("JP-1", "http://www.gstatic.com/generate_204", 5000)
    assert d.delay == 137
    await clash.aclose()


async def test_close_connection_endpoints(clash: Clash) -> None:
    await clash.close_connection("abc-123")
    await clash.close_all_connections()
    await clash.aclose()


# --- error mapping ---------------------------------------------------------


async def test_404_maps_to_not_found(clash: Clash) -> None:
    with pytest.raises(NotFoundError):
        await clash.proxy("NoSuchProxy")
    await clash.aclose()


async def test_auth_error_maps() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad secret")

    transport = httpx.MockTransport(handler)
    c = _make_client(transport)
    with pytest.raises(AuthError):
        await c.version()
    await c.aclose()


# --- streaming -------------------------------------------------------------


async def test_stream_traffic_yields_parsed_models() -> None:
    body = (FIXTURES / "traffic.ndjson").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/traffic")
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    c = _make_client(transport)
    samples = []
    async for t in stream_traffic(c):
        samples.append(t)
    assert [(s.up, s.down) for s in samples] == [
        (100, 200),
        (150, 250),
        (200, 300),
    ]
    await c.aclose()


async def test_stream_logs_yields_parsed_models() -> None:
    body = (FIXTURES / "logs.ndjson").read_bytes()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    c = _make_client(transport)
    items = []
    async for line in stream_logs(c):
        items.append(line)
    assert len(items) == 4
    assert items[0].level is LogLevel.Info
    assert items[1].level is LogLevel.Warning
    assert items[2].level is LogLevel.Error
    assert items[3].level is LogLevel.Warning  # "warn" alias
    await c.aclose()


async def test_stream_skips_malformed_lines() -> None:
    body = b"not json\n" + b'{"up":1,"down":2}\n'

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    c = _make_client(transport)
    samples: list = []
    async for t in stream_traffic(c):
        samples.append(t)
    assert len(samples) == 1
    assert samples[0].up == 1
    await c.aclose()


# --- lifecycle -------------------------------------------------------------


async def test_async_context_manager(mock_transport: httpx.MockTransport) -> None:
    async with _make_client(mock_transport) as c:
        v = await c.version()
        assert v.version == "v1.18.0"


async def test_authorization_header_sent() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"version": "v1", "premium": False})

    transport = httpx.MockTransport(handler)
    c = _make_client(transport)
    await c.version()
    assert seen == ["Bearer hunter2"]
    await c.aclose()


async def test_no_authorization_header_when_secret_missing() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"version": "v1", "premium": False})

    transport = httpx.MockTransport(handler)
    c = Clash("http://127.0.0.1:9090")
    c._client = httpx.AsyncClient(base_url=c.base_url, transport=transport)  # type: ignore[attr-defined]
    await c.version()
    assert seen == [None]
    await c.aclose()


# --- ensure stream_lines is reachable directly (sanity) --------------------


async def test_stream_lines_strips_blank() -> None:
    """Empty lines in the body should not produce items."""
    body = b'{"up":1,"down":2}\n\n\n{"up":3,"down":4}\n'

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    c = _make_client(transport)
    out: list = []
    async for t in stream_traffic(c):
        out.append(t)
    assert [(t.up, t.down) for t in out] == [(1, 2), (3, 4)]
    await c.aclose()


# Type-check: AsyncIterator import used so ruff doesn't complain.
_: type = AsyncIterator
