from __future__ import annotations

from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from clashctl_py.api.errors import (
    AuthError,
    ClashError,
    HTTPStatusError,
    NotFoundError,
)
from clashctl_py.models import (
    ClashConfig,
    Connections,
    Delay,
    Proxies,
    Proxy,
    Rules,
    Version,
)


class Clash:
    """Async client for the Clash external-controller REST API.

    Streaming endpoints (`/traffic`, `/logs`) live in `api.streams` so the
    client itself can keep a single bounded HTTP timeout.
    """

    def __init__(
        self,
        base_url: str,
        secret: str | None = None,
        timeout_ms: int = 5000,
    ) -> None:
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        headers: dict[str, str] = {}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        self._base_url = base_url
        self._secret = secret
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout_ms / 1000,
        )
        # Separate client without timeout for long-haul streams; lazily created.
        self._stream_client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def secret(self) -> str | None:
        return self._secret

    def stream_client(self) -> httpx.AsyncClient:
        """Long-lived client without read timeout, for /traffic and /logs."""
        if self._stream_client is None:
            headers: dict[str, str] = {}
            if self._secret:
                headers["Authorization"] = f"Bearer {self._secret}"
            self._stream_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0),
            )
        return self._stream_client

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()
        if self._stream_client is not None:
            await self._stream_client.aclose()

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            resp = await self._client.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise ClashError(f"transport error: {e}") from e
        self._check_status(resp)
        return resp

    @staticmethod
    def _check_status(resp: httpx.Response) -> None:
        sc = resp.status_code
        if sc < 400:
            return
        if sc in (401, 403):
            raise AuthError(f"authentication failed (HTTP {sc})")
        if sc == 404:
            raise NotFoundError(f"not found: {resp.request.url}")
        raise HTTPStatusError(sc, resp.text[:200])

    # --- one-shot endpoints -------------------------------------------------

    async def version(self) -> Version:
        r = await self._request("GET", "version")
        return Version.model_validate_json(r.content)

    async def configs(self) -> ClashConfig:
        r = await self._request("GET", "configs")
        return ClashConfig.model_validate_json(r.content)

    async def reload_configs(self, path: str, force: bool = False) -> None:
        endpoint = "configs?force" if force else "configs"
        await self._request("PUT", endpoint, json={"path": path})

    async def proxies(self) -> Proxies:
        r = await self._request("GET", "proxies")
        # Clash returns `{"proxies": {...}}`; unwrap.
        data = r.json()
        inner = data.get("proxies", data)
        return Proxies.model_validate(inner)

    async def proxy(self, name: str) -> Proxy:
        r = await self._request("GET", f"proxies/{quote(name, safe='')}")
        return Proxy.model_validate_json(r.content)

    async def rules(self) -> Rules:
        r = await self._request("GET", "rules")
        return Rules.model_validate_json(r.content)

    async def connections(self) -> Connections:
        r = await self._request("GET", "connections")
        return Connections.model_validate_json(r.content)

    async def close_connection(self, conn_id: str) -> None:
        await self._request("DELETE", f"connections/{quote(conn_id, safe='')}")

    async def close_all_connections(self) -> None:
        await self._request("DELETE", "connections")

    async def select(self, group: str, proxy: str) -> None:
        """Switch a Selector group's active member."""
        await self._request(
            "PUT",
            f"proxies/{quote(group, safe='')}",
            json={"name": proxy},
        )

    async def delay(self, proxy: str, test_url: str, timeout_ms: int) -> Delay:
        """Probe a single proxy's latency. Raises on connection failure."""
        r = await self._request(
            "GET",
            f"proxies/{quote(proxy, safe='')}/delay",
            params={"url": test_url, "timeout": timeout_ms},
        )
        return Delay.model_validate_json(r.content)
