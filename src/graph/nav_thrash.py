"""Pure navigation thrash scoring — no I/O, no emulator.

Used so outdoor loops that *do* change position (2-tile oscillation, map
bounce) still raise stuck_count and engage M3/M11 recovery.
"""

from __future__ import annotations

from typing import Sequence

# One position sample: (map_key, x, y)
NavPos = tuple[str, int, int]


def nav_thrash_severity(
    history: Sequence[NavPos],
    *,
    window: int = 12,
) -> int:
    """Return thrash severity (≥1 means treat as stuck).

    Signals (any triggers ≥1; stronger thrash can score higher):
    (a) ≤2 unique tiles in the window (same-tile freeze or 2-tile pocket)
    (b) 2-tile A↔B oscillation with ≥3 direction flips
    (c) map_key flip-flops ≥2 times in the window

    Empty / short histories return 0. Pure function — no I/O.
    """
    if window < 2:
        window = 2
    if not history:
        return 0
    recent = list(history[-window:])
    if len(recent) < 4:
        # Need a few samples before calling thrash (avoid false stuck on start).
        return 0

    severity = 0

    # (c) Map-key flip-flops first (warp bounce 26:2↔26:1).
    maps = [m for m, _x, _y in recent]
    map_flips = sum(1 for a, b in zip(maps, maps[1:]) if a != b)
    if map_flips >= 2:
        severity = max(severity, 1 + min(2, map_flips - 2))

    # Unique tiles (map,x,y).
    unique = set(recent)
    n_unique = len(unique)

    # (a) Tiny position set while still moving through history.
    if n_unique <= 2 and len(recent) >= 6:
        severity = max(severity, 1 if n_unique == 2 else 2)

    # (b) 2-tile oscillation with enough A↔B cycles.
    if n_unique == 2 and len(recent) >= 6:
        a, b = tuple(unique)
        flips = 0
        for prev, cur in zip(recent, recent[1:]):
            if prev != cur and {prev, cur} == {a, b}:
                flips += 1
        # ≥3 flips ≈ 1.5 full cycles; require solid thrash.
        if flips >= 3:
            severity = max(severity, 1 + min(2, flips // 3))

    # Same-tile freeze: many samples one tile (also covered by n_unique==1).
    if n_unique == 1 and len(recent) >= 6:
        severity = max(severity, 2)

    # (d) Compact multi-tile pocket (live R31 x24–25 y11–15 thrash with stuck=0):
    # many samples inside a small bounding box, not a progressing corridor.
    if len(recent) >= 10 and 3 <= n_unique <= 8:
        xs = [x for _m, x, _y in recent]
        ys = [y for _m, _x, y in recent]
        maps = {m for m, _x, _y in recent}
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        # Pocket ≤3×5 tiles on one map; exclude long corridors (width≥6).
        if len(maps) == 1 and width <= 3 and height <= 5 and (width + height) >= 1:
            severity = max(severity, 1)

    return severity


def append_nav_position(
    positions: list[NavPos] | None,
    map_key: str,
    x: int,
    y: int,
    *,
    max_len: int = 24,
) -> list[NavPos]:
    """Append a sample and cap length (helper for graph state)."""
    out = list(positions or [])
    out.append((map_key, int(x), int(y)))
    if len(out) > max_len:
        out = out[-max_len:]
    return out
