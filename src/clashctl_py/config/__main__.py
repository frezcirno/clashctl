"""`python -m clashctl_py.config show` — print the resolved config.

Useful for debugging path resolution and TOML parse issues during dev.
"""

from __future__ import annotations

import json
import sys

from clashctl_py.config import default_config_path, load_config


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] != "show":
        print("usage: python -m clashctl_py.config show", file=sys.stderr)
        return 2

    path = default_config_path()
    print(f"# config path: {path}", file=sys.stderr)
    print(f"# exists:      {path.exists()}", file=sys.stderr)
    cfg = load_config(path)
    print(json.dumps(cfg.model_dump(mode="json", exclude_none=True), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
