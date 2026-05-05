from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from clashctl_py.api.client import Clash
from clashctl_py.api.errors import StreamError
from clashctl_py.models import LogLine, Traffic

log = logging.getLogger(__name__)


async def stream_traffic(client: Clash) -> AsyncIterator[Traffic]:
    """Yield Traffic samples from `/traffic` until the connection drops."""
    async for line in _stream_lines(client, "traffic"):
        try:
            yield Traffic.model_validate_json(line)
        except ValueError as e:
            log.debug("skipping bad /traffic line %r: %s", line[:80], e)


async def stream_logs(client: Clash) -> AsyncIterator[LogLine]:
    """Yield LogLine items from `/logs` until the connection drops."""
    async for line in _stream_lines(client, "logs"):
        try:
            yield LogLine.model_validate_json(line)
        except ValueError as e:
            log.debug("skipping bad /logs line %r: %s", line[:80], e)


async def _stream_lines(client: Clash, path: str) -> AsyncIterator[str]:
    """Open a streaming GET and yield each non-empty line."""
    sc = client.stream_client()
    try:
        async with sc.stream("GET", path) as resp:
            if resp.status_code >= 400:
                raise StreamError(f"{path} returned HTTP {resp.status_code}")
            async for raw in resp.aiter_lines():
                line = raw.strip()
                if line:
                    yield line
    except httpx.HTTPError as e:
        raise StreamError(f"{path} disconnected: {e}") from e
