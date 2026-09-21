"""Canonical time grid (MVP.md §3.1, §5): Δt = 5 minutes, UTC.

`expand()` places a coarser native sample onto the grid: the first slot keeps the native
quality (`measured`), the remaining slots are flagged `interpolated` (value held — a period
average applies to its whole period), while `resolution` always records the native step.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from emap.schema import Quality, Resolution

STEP = timedelta(minutes=5)
CANONICAL_RESOLUTION: Resolution = "PT5M"
_NATIVE_STEP: dict[Resolution, timedelta] = {
    "PT5M": timedelta(minutes=5),
    "PT15M": timedelta(minutes=15),
    "PT60M": timedelta(minutes=60),
}


def floor_to_grid(t: datetime) -> datetime:
    """Largest grid instant <= t."""
    return t - timedelta(minutes=t.minute % 5, seconds=t.second, microseconds=t.microsecond)


def expand(t: datetime, resolution: Resolution) -> Iterator[tuple[datetime, Quality]]:
    """Grid slots covered by a native sample starting at `t` with the given native resolution."""
    n = _NATIVE_STEP[resolution] // STEP
    for i in range(n):
        yield t + i * STEP, ("measured" if i == 0 else "interpolated")
