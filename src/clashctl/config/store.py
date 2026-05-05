"""Loading and saving the TOML config file."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir

from clashctl.config.schema import AppConfig

_APP_NAME = "clashctl"
_CONFIG_FILENAME = "config.toml"


def default_config_path() -> Path:
    """Return the canonical config path, respecting `CLASHCTL_CONFIG_PATH`.

    Falls back to `<user_config_dir>/clashctl/config.toml` (XDG on Linux,
    AppData on Windows, ~/Library/Application Support on macOS).
    """
    override = os.environ.get("CLASHCTL_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir(_APP_NAME)) / _CONFIG_FILENAME


def load_config(path: Path | None = None) -> AppConfig:
    """Read and validate the config file. Returns defaults if missing."""
    p = path or default_config_path()
    if not p.exists():
        return AppConfig()
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    return AppConfig.model_validate(raw)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """Atomically write `config` to `path`. Creates parent dirs as needed.

    Returns the path written.
    """
    p = path or default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    # `model_dump(mode="json")` coerces enums to their string values, which
    # is what tomli_w expects. `exclude_none=True` keeps the file tidy.
    data: dict[str, Any] = config.model_dump(mode="json", exclude_none=True)
    payload = tomli_w.dumps(data)

    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, p)
    return p
