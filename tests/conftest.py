from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def fixture_json(name: str) -> dict | list:
    return json.loads(fixture_text(name))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    """Routes Clash endpoints to our recorded fixtures."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.lstrip("/")
        if path == "version":
            return httpx.Response(200, text=fixture_text("version.json"))
        if path == "configs":
            if request.method == "PUT":
                return httpx.Response(204)
            return httpx.Response(200, text=fixture_text("configs.json"))
        if path == "proxies":
            return httpx.Response(200, text=fixture_text("proxies.json"))
        if path.startswith("proxies/") and path.endswith("/delay"):
            return httpx.Response(200, text=fixture_text("delay.json"))
        if path.startswith("proxies/") and request.method == "PUT":
            return httpx.Response(204)
        if path.startswith("proxies/"):
            # Single proxy — return one entry from proxies.json
            data = fixture_json("proxies.json")
            assert isinstance(data, dict)
            name = path.removeprefix("proxies/")
            inner = data["proxies"]
            assert isinstance(inner, dict)
            if name in inner:
                return httpx.Response(200, json=inner[name])
            return httpx.Response(404, text="not found")
        if path == "rules":
            return httpx.Response(200, text=fixture_text("rules.json"))
        if path == "connections":
            if request.method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(200, text=fixture_text("connections.json"))
        if path.startswith("connections/") and request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, text=f"unhandled path: {path}")

    return httpx.MockTransport(handler)
