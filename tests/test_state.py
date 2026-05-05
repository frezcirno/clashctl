from __future__ import annotations

from datetime import UTC, datetime

from clashctl_py.models import Connection, Metadata, RuleType
from clashctl_py.state import ConnectionSpeedTracker


def _conn(cid: str, upload: int, download: int) -> Connection:
    return Connection(
        id=cid,
        upload=upload,
        download=download,
        metadata=Metadata(
            type="HTTP",
            sourceIP="10.0.0.1",
            source_port="1000",
            destinationIP="1.1.1.1",
            destination_port="443",
            host="x.com",
            network="tcp",
        ),
        rule=RuleType.Match,
        rule_payload="",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        chains=[],
    )


def test_first_sighting_yields_zero_speed() -> None:
    t = ConnectionSpeedTracker()
    [r] = t.update([_conn("a", upload=100, download=200)], now=10.0)
    assert r.upload_speed == 0
    assert r.download_speed == 0


def test_speed_is_diff_per_second() -> None:
    t = ConnectionSpeedTracker()
    t.update([_conn("a", upload=0, download=0)], now=10.0)
    [r] = t.update([_conn("a", upload=300, download=600)], now=11.0)
    assert r.upload_speed == 300
    assert r.download_speed == 600


def test_fractional_seconds() -> None:
    t = ConnectionSpeedTracker()
    t.update([_conn("a", upload=0, download=0)], now=10.0)
    # 0.5 second elapsed, 200 bytes ⇒ 400 B/s
    [r] = t.update([_conn("a", upload=200, download=400)], now=10.5)
    assert r.upload_speed == 400
    assert r.download_speed == 800


def test_counter_reset_yields_zero() -> None:
    """Clash restart drops totals; emit 0 rather than a huge negative."""
    t = ConnectionSpeedTracker()
    t.update([_conn("a", upload=1000, download=1000)], now=10.0)
    [r] = t.update([_conn("a", upload=10, download=10)], now=11.0)
    assert r.upload_speed == 0
    assert r.download_speed == 0


def test_disappearing_connection_drops_from_cache() -> None:
    t = ConnectionSpeedTracker()
    t.update([_conn("a", upload=0, download=0)], now=10.0)
    t.update([_conn("b", upload=0, download=0)], now=11.0)
    # "a" should be gone; if it reappears, treat it as a new sighting.
    [r] = t.update([_conn("a", upload=500, download=500)], now=12.0)
    assert r.upload_speed == 0
    assert r.download_speed == 0


def test_simultaneous_tick_yields_zero() -> None:
    """If two ticks share a timestamp, dt=0; just emit zero (no /0)."""
    t = ConnectionSpeedTracker()
    t.update([_conn("a", upload=0, download=0)], now=10.0)
    [r] = t.update([_conn("a", upload=100, download=100)], now=10.0)
    assert r.upload_speed == 0
    assert r.download_speed == 0


def test_multi_connection_tracking() -> None:
    t = ConnectionSpeedTracker()
    t.update(
        [_conn("a", upload=0, download=0), _conn("b", upload=0, download=0)],
        now=10.0,
    )
    out = t.update(
        [_conn("a", upload=100, download=200), _conn("b", upload=300, download=400)],
        now=11.0,
    )
    assert {(r.connection.id, r.upload_speed, r.download_speed) for r in out} == {
        ("a", 100, 200),
        ("b", 300, 400),
    }


def test_reset_clears_history() -> None:
    t = ConnectionSpeedTracker()
    t.update([_conn("a", upload=0, download=0)], now=10.0)
    t.reset()
    [r] = t.update([_conn("a", upload=500, download=500)], now=11.0)
    assert r.upload_speed == 0
    assert r.download_speed == 0
