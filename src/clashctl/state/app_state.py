"""Central in-memory state for the running TUI.

Pure Python — no Textual imports. Reducers are sync mutators called by
the App's message handlers; they don't perform any I/O themselves.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import monotonic

from clashctl.models import (
    ClashConfig,
    Connections,
    LogLine,
    Proxies,
    Rules,
    Traffic,
    Version,
)
from clashctl.state.speed import ConnectionSpeedTracker, ConnectionWithSpeed


@dataclass
class AppState:
    """Single source of truth for the TUI."""

    # Configurable buffer sizes (set from AppConfig.ui at construction).
    traffic_maxlen: int = 500
    log_maxlen: int = 2000

    # Snapshot data (replaced wholesale on each update)
    version: Version | None = None
    clash_config: ClashConfig | None = None
    proxies: Proxies | None = None
    rules: Rules | None = None
    rule_frequency: dict[str, int] = field(default_factory=dict)
    connections: list[ConnectionWithSpeed] = field(default_factory=list)
    connection_totals: tuple[int, int] = (0, 0)  # (upload_total, download_total)

    # Name of the proxy group currently being latency-tested, or None.
    testing_group: str | None = None

    # Append-only buffers
    traffic_history: deque[Traffic] = field(init=False)
    logs: deque[LogLine] = field(init=False)

    # Derived running stats
    max_traffic: Traffic = field(default_factory=Traffic)

    # Diagnostics
    last_error: tuple[str, str] | None = None  # (source, message)
    started_at: float = field(default_factory=monotonic)

    # Internal collaborators
    _speed_tracker: ConnectionSpeedTracker = field(
        default_factory=ConnectionSpeedTracker
    )

    def __post_init__(self) -> None:
        self.traffic_history = deque(maxlen=self.traffic_maxlen)
        self.logs = deque(maxlen=self.log_maxlen)

    # --- reducers ---------------------------------------------------------

    def apply_version(self, v: Version) -> None:
        self.version = v

    def apply_config(self, c: ClashConfig) -> None:
        self.clash_config = c

    def apply_proxies(self, p: Proxies) -> None:
        self.proxies = p

    def apply_rules(self, r: Rules) -> None:
        self.rules = r
        self.rule_frequency = r.frequency()

    def apply_connections(self, c: Connections) -> None:
        self.connections = self._speed_tracker.update(c.connections)
        self.connection_totals = (c.upload_total, c.download_total)

    def apply_traffic(self, t: Traffic) -> None:
        self.traffic_history.append(t)
        if t.up > self.max_traffic.up:
            self.max_traffic = Traffic(up=t.up, down=self.max_traffic.down)
        if t.down > self.max_traffic.down:
            self.max_traffic = Traffic(up=self.max_traffic.up, down=t.down)

    def apply_log(self, line: LogLine) -> None:
        self.logs.append(line)

    def record_error(self, source: str, message: str) -> None:
        self.last_error = (source, message)

    def clear_error(self) -> None:
        self.last_error = None

    # --- helpers used by the placeholder MainScreen + tests --------------

    def reset_for_new_server(self) -> None:
        """Wipe all server-specific state (used on Ctrl-S server switch)."""
        self.version = None
        self.clash_config = None
        self.proxies = None
        self.rules = None
        self.rule_frequency = {}
        self.connections = []
        self.connection_totals = (0, 0)
        self.testing_group = None
        self.traffic_history.clear()
        self.logs.clear()
        self.max_traffic = Traffic()
        self.last_error = None
        self._speed_tracker.reset()
        self.started_at = monotonic()

    def summary(self) -> str:
        """Plain-text dump used by the Phase 3 placeholder dashboard."""
        elapsed = int(monotonic() - self.started_at)
        last = self.traffic_history[-1] if self.traffic_history else Traffic()
        n_proxies = len(self.proxies) if self.proxies is not None else 0
        n_groups = (
            sum(1 for _ in self.proxies.groups()) if self.proxies is not None else 0
        )
        n_rules = len(self.rules.rules) if self.rules is not None else 0
        n_conns = len(self.connections)
        ver = self.version.version if self.version is not None else "?"
        err = (
            f"!! {self.last_error[0]}: {self.last_error[1]}"
            if self.last_error
            else "ok"
        )
        return (
            f"[clashctl-py @ {elapsed}s]  status: {err}\n"
            f"clash version: {ver}\n"
            f"connections:   {n_conns} active   "
            f"(↑ total {self.connection_totals[0]:>10}  "
            f"↓ total {self.connection_totals[1]:>10})\n"
            f"current:       ↑ {last.up:>10} B/s   ↓ {last.down:>10} B/s\n"
            f"max:           ↑ {self.max_traffic.up:>10} B/s   "
            f"↓ {self.max_traffic.down:>10} B/s\n"
            f"proxies:       {n_proxies} total ({n_groups} groups)\n"
            f"rules:         {n_rules}\n"
            f"traffic samples: {len(self.traffic_history)}     "
            f"log lines: {len(self.logs)}"
        )
