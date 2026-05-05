from __future__ import annotations

import pytest

from clashctl_py.utils.bytesize import humanize_bytes, humanize_rate


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, "0 B"),
        (1, "1 B"),
        (1023, "1023 B"),
        (1024, "1.00 KiB"),
        (1500, "1.46 KiB"),
        (1024 * 10, "10.0 KiB"),
        (1024 * 100, "100 KiB"),
        (1024 * 1024, "1.00 MiB"),
        (15_000_000, "14.3 MiB"),
        (1_500_000_000, "1.40 GiB"),
        (1024**4, "1.00 TiB"),
        (1024**5, "1.00 PiB"),
    ],
)
def test_humanize_bytes(n: int, expected: str) -> None:
    assert humanize_bytes(n) == expected


def test_humanize_bytes_negative() -> None:
    assert humanize_bytes(-2048).startswith("-")
    assert "KiB" in humanize_bytes(-2048)


def test_humanize_rate_appends_per_second() -> None:
    assert humanize_rate(1024).endswith("/s")
    assert humanize_rate(0) == "0 B/s"
