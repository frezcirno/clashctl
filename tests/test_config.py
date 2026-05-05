from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from clashctl.config import (
    AppConfig,
    Server,
    default_config_path,
    load_config,
    save_config,
)
from clashctl.state import ConnSortBy, Order, ProxySortBy, RuleSortBy

# --- Server ---------------------------------------------------------------


def test_server_empty_secret_coerced_to_none() -> None:
    s = Server(name="local", url="http://127.0.0.1:9090", secret="")
    assert s.secret is None


def test_server_secret_preserved_when_set() -> None:
    s = Server(name="x", url="http://127.0.0.1:9090", secret="abc")
    assert s.secret == "abc"


@pytest.mark.parametrize(
    "url",
    ["", "ftp://x", "no-scheme", "http://", "https:///nohost"],
)
def test_server_rejects_bad_url(url: str) -> None:
    with pytest.raises(ValidationError):
        Server(name="x", url=url)


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:9090", "https://proxy.example.com/", "http://localhost:9090"],
)
def test_server_accepts_good_url(url: str) -> None:
    Server(name="x", url=url)


# --- AppConfig manipulation -----------------------------------------------


def test_add_first_server_sets_using() -> None:
    cfg = AppConfig()
    cfg.add_server(Server(name="a", url="http://127.0.0.1:9090"))
    assert cfg.using == "http://127.0.0.1:9090"


def test_add_duplicate_server_rejected() -> None:
    cfg = AppConfig()
    s = Server(name="a", url="http://127.0.0.1:9090")
    cfg.add_server(s)
    with pytest.raises(ValueError, match="already exists"):
        cfg.add_server(s)


def test_use_unknown_url_rejected() -> None:
    cfg = AppConfig()
    with pytest.raises(ValueError, match="not found"):
        cfg.use("http://nope")


def test_remove_using_server_picks_next() -> None:
    cfg = AppConfig()
    cfg.add_server(Server(name="a", url="http://a.local:9090"))
    cfg.add_server(Server(name="b", url="http://b.local:9090"))
    cfg.use("http://a.local:9090")
    cfg.remove_server("http://a.local:9090")
    assert cfg.using == "http://b.local:9090"


def test_remove_last_server_clears_using() -> None:
    cfg = AppConfig()
    cfg.add_server(Server(name="a", url="http://a.local:9090"))
    cfg.remove_server("http://a.local:9090")
    assert cfg.using is None
    assert cfg.servers == []


def test_using_server_returns_none_for_unconfigured() -> None:
    assert AppConfig().using_server() is None


def test_using_server_returns_match() -> None:
    cfg = AppConfig()
    s = Server(name="a", url="http://a:9090")
    cfg.add_server(s)
    assert cfg.using_server() == s


# --- TOML round-trip ------------------------------------------------------


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.servers == []
    assert cfg.using is None
    assert cfg.ui.test_url.startswith("http")


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig()
    cfg.add_server(Server(name="local", url="http://127.0.0.1:9090", secret="hunter2"))
    cfg.add_server(Server(name="remote", url="http://r.example:9090"))
    cfg.use("http://r.example:9090")

    save_config(cfg, path)
    assert path.exists()
    loaded = load_config(path)
    assert loaded == cfg


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "more" / "config.toml"
    save_config(AppConfig(), path)
    assert path.exists()


def test_save_omits_none_secret(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig()
    cfg.add_server(Server(name="x", url="http://x:9090"))  # no secret
    save_config(cfg, path)
    raw = path.read_text()
    assert "secret" not in raw


def test_default_config_path_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLASHCTL_CONFIG_PATH", "/tmp/custom-clashctl.toml")
    assert default_config_path() == Path("/tmp/custom-clashctl.toml")


def test_default_config_path_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLASHCTL_CONFIG_PATH", raising=False)
    p = default_config_path()
    assert p.name == "config.toml"
    assert "clashctl" in str(p)


# --- Sort defaults persisted correctly ------------------------------------


def test_default_sorts_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig()
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.ui.sort.proxies.by is ProxySortBy.Delay
    assert loaded.ui.sort.proxies.order is Order.Asc
    assert loaded.ui.sort.rules.by is RuleSortBy.Payload
    assert loaded.ui.sort.connections.by is ConnSortBy.Time
    assert loaded.ui.sort.connections.order is Order.Desc


def test_partial_toml_fills_in_defaults(tmp_path: Path) -> None:
    """User-edited config that only specifies one server should still load."""
    path = tmp_path / "config.toml"
    path.write_text(
        'using = "http://127.0.0.1:9090"\n\n'
        "[[servers]]\n"
        'name = "local"\n'
        'url = "http://127.0.0.1:9090"\n'
    )
    cfg = load_config(path)
    assert cfg.using == "http://127.0.0.1:9090"
    assert len(cfg.servers) == 1
    # UI block missing → defaults filled in.
    assert cfg.ui.refresh_slow_secs == 5.0


def test_atomic_write_via_tmp_then_replace(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_config(AppConfig(), path)
    # No lingering .tmp file.
    siblings = {p.name for p in tmp_path.iterdir()}
    assert "config.toml" in siblings
    assert "config.toml.tmp" not in siblings


def test_to_runtime_sort_constructs_proper_objects() -> None:
    cfg = AppConfig()
    p, r, c = cfg.ui.sort.to_runtime()
    assert p.by is ProxySortBy.Delay
    assert r.by is RuleSortBy.Payload
    assert c.by is ConnSortBy.Time


# Sanity: the env-override used by default_config_path doesn't leak between
# tests (monkeypatch does its own cleanup; this just documents intent).
def test_env_override_isolation() -> None:
    assert (
        "CLASHCTL_CONFIG_PATH" not in os.environ
        or os.environ["CLASHCTL_CONFIG_PATH"] != "/tmp/custom-clashctl.toml"
    )
