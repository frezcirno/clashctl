"""Format byte counts using IEC binary units (KiB, MiB, ...).

Matches the Rust `bytesize` crate's binary mode output: short, fixed-width
strings suitable for tightly-packed status panels.
"""

from __future__ import annotations

_UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")


def humanize_bytes(n: float) -> str:
    """Render `n` bytes with two significant digits and an IEC unit.

    Examples:
        >>> humanize_bytes(0)
        '0 B'
        >>> humanize_bytes(1023)
        '1023 B'
        >>> humanize_bytes(1024)
        '1.00 KiB'
        >>> humanize_bytes(1500)
        '1.46 KiB'
        >>> humanize_bytes(15_000_000)
        '14.3 MiB'
        >>> humanize_bytes(1_500_000_000)
        '1.40 GiB'
    """
    if n < 0:
        return "-" + humanize_bytes(-n)
    f = float(n)
    i = 0
    while f >= 1024 and i < len(_UNITS) - 1:
        f /= 1024.0
        i += 1
    if i == 0:
        return f"{int(f)} {_UNITS[i]}"
    if f >= 100:
        return f"{f:.0f} {_UNITS[i]}"
    if f >= 10:
        return f"{f:.1f} {_UNITS[i]}"
    return f"{f:.2f} {_UNITS[i]}"


def humanize_rate(n: float) -> str:
    """Same formatting as humanize_bytes, with a `/s` suffix."""
    return humanize_bytes(n) + "/s"
