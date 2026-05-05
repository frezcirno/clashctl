# clashctl-py

Python 3 rewrite of [clashctl](https://github.com/George-Miao/clashctl) — a [Textual](https://textual.textualize.io/)-based TUI for the [Clash](https://github.com/Dreamacro/clash) (and [mihomo](https://github.com/MetaCubeX/mihomo)) external-controller REST API.

A live dashboard with five tabs: **Status / Proxies / Rules / Conns / Logs**. Server management lives entirely inside the TUI — no `add`/`use`/`del` subcommands.

```text
┌─ Status ───────────────────────────────────────────────────┐
│ ⇉ Connections        12 │  ▲ ▁▁▃▂▄▇▆▆▅▇▆▆▆▆▇▆▅▆▇▆▆▇▇▆▇▆▆▇  │
│ ▲ Upload     12.4 KiB/s │  ▼ ▁▂▁▁▂▁▁▁▁▂▂▂▂▁▂▂▁▂▁▂▁▂▁▁▂▁▂▁  │
│ ▼ Download    1.2 MiB/s │                                  │
│ ▲ Avg.        9.1 KiB/s │  max ↑ 487 KiB/s  ↓ 4.3 MiB/s    │
│ ▼ Avg.        812 KiB/s │                                  │
│ Clash Ver.      v1.18.0 │                                  │
└────────────────────────────────────────────────────────────┘
```

## Status

**MVP complete** — all five tabs functional, in-TUI server management, 213 unit tests, headless E2E verified.

Notable differences from the Rust original:

- **Real instantaneous connection speeds** (the Rust version reports `total_bytes / seconds_since_connection_start`, which mis-represents short bursts; here speeds are computed by diffing successive `/connections` polls).
- **`ConnSort` is actually implemented** (the Rust counterpart was `todo!()` for all 11 keys).
- **Config in TOML** instead of RON.
- **Server management lives in the TUI**, not in CLI subcommands.

## Install

```bash
cd clashctl-py
pip install -e ".[dev]"           # editable + test deps
# or, with uv:
uv pip install -e ".[dev]"
```

Python 3.11 or newer is required.

## Run

```bash
clashctl                           # default config path
clashctl -c /path/to/config.toml   # custom path
clashctl --debug                   # verbose log to /tmp/clashctl.log
```

On first launch with no configured server, a modal pops up and walks you through adding one. The form probes `/version` against the supplied URL before saving so typos and bad secrets are caught early.

## Keybindings

### Global (any tab)

| Key | Action |
|---|---|
| `q`, `Ctrl+C` | Quit |
| `1`–`5` | Switch tabs |
| `Ctrl+S` | Open the server picker (add / delete / switch) |

### Tab-specific

| Tab     | Key                  | Action                                                                                       |
|---------|----------------------|----------------------------------------------------------------------------------------------|
| Proxies | `t`                  | Test latency for the focused group's normal members (parallel, capped at 8)                  |
| Proxies | `Enter`              | On a member of a Selector group: switch to it (PUT `/proxies/<group>`)                       |
| Proxies | `s` / `Shift+s`      | Cycle member sort (name / type / delay × asc / desc)                                         |
| Rules   | `s` / `Shift+s`      | Cycle sort (payload / type / proxy × asc / desc)                                             |
| Rules   | `Space`              | Toggle HOLD mode (cursor pinned across refreshes)                                            |
| Rules   | `↑↓`                 | Navigate (in HOLD)                                                                           |
| Rules   | `Esc`                | Exit HOLD                                                                                    |
| Conns   | `s` / `Shift+s`      | Cycle sort across 11 keys (host, ▼, ▲, speeds, time, rule, chain, src, dst, type) × asc/desc |
| Conns   | `Space`, `Esc`, `↑↓` | Same HOLD behavior as Rules                                                                  |

### Server picker

| Key | Action |
|---|---|
| `a` | Add a new server (opens form) |
| `d` | Delete the focused server |
| `u` / `Enter` | Use the focused server (swaps connections) |
| `Esc` | Close (or quit on first run) |

## Config

Stored at `~/.config/clashctl/config.toml` by default (respects `$XDG_CONFIG_HOME`; on macOS it lands under `~/Library/Application Support/clashctl/`). Override the path with `-c <path>` or `CLASHCTL_CONFIG_PATH=...`.

Schema:

```toml
using = "http://127.0.0.1:9090"

[[servers]]
name = "local"
url = "http://127.0.0.1:9090"
secret = ""                             # empty == no auth

[[servers]]
name = "remote"
url = "https://proxy.example.com:9090"
secret = "hunter2"

[ui]
test_url = "http://www.gstatic.com/generate_204"
test_timeout_ms = 5000
log_buffer = 2000                       # in-memory log line cap
traffic_history = 500                   # sparkline samples
refresh_slow_secs = 5.0                 # /version, /configs, /proxies, /rules
refresh_fast_secs = 1.0                 # /connections

[ui.sort]
proxies     = { by = "delay",   order = "asc"  }
rules       = { by = "payload", order = "asc"  }
connections = { by = "time",    order = "desc" }
```

The TOML can be hand-edited; the TUI rewrites it via `tomli_w` whenever you add/use/delete a server.

## Architecture

```text
src/clashctl/
├── api/        # httpx async client + line-delimited JSON streams
├── models/     # pydantic v2 models for every Clash payload
├── state/      # AppState (single source of truth) + sort + speed tracker
├── config/     # TOML load/save + AppConfig schema
├── tui/        # Textual app, screens, widgets, polling worker
└── utils/      # bytesize / duration helpers
```

- **Pollers** are plain asyncio classes that post `Message`s up the Textual tree; the App reduces messages into `AppState` and tells the active screen what to refresh.
- **Layering rule**: `api/`, `models/`, `state/`, `config/` never import Textual — they're unit-testable without spinning up an `App`.
- **Hidden tabs**: `RichLog.write()` produces empty strips when the widget has no width, so the Logs tab buffers in `AppState.logs` and replays on tab activation.

## Test

```bash
pytest                  # 213 tests, ~9s
ruff check src tests    # lint
mypy src                # type check (strict mode)
```

Tests are split between pure unit coverage (models, sort, speed tracker, config round-trip) and Textual `run_test()` harnesses for widgets and screens. The API client is exercised against `httpx.MockTransport` with recorded fixtures under `tests/fixtures/`.

## License

MIT — see [LICENSE](../LICENSE).
