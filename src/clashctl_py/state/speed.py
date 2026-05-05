"""Per-connection instantaneous speed tracking.

The Rust version computed `total_bytes / seconds_since_connection_start`,
which makes long-running idle connections look fast and short bursts look
slow. We keep the previous tick's cumulative byte count per connection id
and emit `(current - previous) / dt` instead.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from clashctl_py.models import Connection


@dataclass(frozen=True)
class ConnectionWithSpeed:
    """A connection enriched with diff-based instantaneous speeds."""

    connection: Connection
    upload_speed: int  # bytes/sec
    download_speed: int  # bytes/sec


class ConnectionSpeedTracker:
    """Stateful tracker that diffs successive `/connections` snapshots.

    Behavior:
    - First sighting of a connection id: speeds reported as 0.
    - Counter regression (current < previous) is treated as a Clash restart
      or an out-of-order tick: speeds reported as 0 for that step.
    - Connections that disappear are dropped from the cache.
    """

    def __init__(self) -> None:
        # id -> (upload_bytes, download_bytes, timestamp_seconds)
        self._prev: dict[str, tuple[int, int, float]] = {}

    def update(
        self,
        connections: list[Connection],
        now: float | None = None,
    ) -> list[ConnectionWithSpeed]:
        if now is None:
            now = time.monotonic()

        out: list[ConnectionWithSpeed] = []
        new_prev: dict[str, tuple[int, int, float]] = {}

        for c in connections:
            prev = self._prev.get(c.id)
            up_speed = down_speed = 0
            if prev is not None:
                pu, pd, pt = prev
                dt = now - pt
                if dt > 0 and c.upload >= pu and c.download >= pd:
                    up_speed = int((c.upload - pu) / dt)
                    down_speed = int((c.download - pd) / dt)
                # else: counter reset / clock skew → keep 0
            new_prev[c.id] = (c.upload, c.download, now)
            out.append(ConnectionWithSpeed(c, up_speed, down_speed))

        self._prev = new_prev
        return out

    def reset(self) -> None:
        """Forget all per-connection history (e.g. on server switch)."""
        self._prev.clear()
