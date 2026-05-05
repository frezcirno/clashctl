"""`clashctl` entrypoint.

The full CLI surface is intentionally minimal — clashctl is a TUI app.
Server management lives inside the TUI (Phase 7).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from clashctl_py import __version__
from clashctl_py.config import default_config_path, load_config
from clashctl_py.tui import ClashCtlApp


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clashctl", description="TUI for the Clash proxy API")
    p.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help=f"path to config TOML (default: {default_config_path()})",
    )
    p.add_argument("--debug", action="store_true", help="enable verbose logging")
    p.add_argument("--version", action="version", version=f"clashctl {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.debug:
        # Textual swallows stdout/stderr in alt-screen; route to a file.
        log_path = os.environ.get("CLASHCTL_DEBUG_LOG", "/tmp/clashctl.log")
        logging.basicConfig(
            filename=log_path,
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    cfg = load_config(args.config)
    app = ClashCtlApp(cfg)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
