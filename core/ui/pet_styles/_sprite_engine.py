"""
Shared rendering machinery for hand-encoded pixel-art pet styles.

Every pet style in this folder that uses a bitmap matrix
(``shiba``, ``cat`` and any future drop-ins like ``goku``,
``samoyed`` …) leans on this module so we don't repeat the
same blit/overlay/scale plumbing in every file.

Conventions
-----------
A *sprite* is a ``list[str]`` where every string is the same length.
Each character is a single-letter palette key. ``.`` is reserved for
"transparent — do not paint this cell". The grid origin (0, 0) is the
**top-left** of the sprite.

An *overlay* is a sparse ``dict[(col, row), str]`` of palette keys
that paint *over* the base body to express the current state (eyes,
mouth, accessories). Overlays are drawn in the order given so callers
can stack them (e.g., closed-eye line + sleep-Z accent).

A *palette* is a ``dict[str, QColor]`` mapping single-letter keys to
their concrete colors. Each style owns its palette; the engine never
introspects palette values, it just looks up the right color.

Why hand-encoded bitmaps?
-------------------------
Procedural vector art (the old bean) does not look like the Codex
Pets reference the user picked. Real pixel-art sprites trade off
flexibility for fidelity — the artist places every pixel, the engine
just blits. That's exactly the trade-off we want here.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from PyQt6.QtGui import QColor, QPainter


# A bitmap is a tuple of equal-length strings.
Bitmap = Sequence[str]

# An overlay maps grid cells to palette characters.
Overlay = Mapping[Tuple[int, int], str]


# ── Validation ─────────────────────────────────────────────────────


def validate_bitmap(bitmap: Bitmap, name: str = "bitmap") -> Tuple[int, int]:
    """Confirm every row in ``bitmap`` has the same length and return
    the grid size as ``(width, height)``.

    Catching ragged rows here means a typo in a sprite definition
    fails fast at import time (when the style module loads) with a
    pointed error message, rather than silently rendering a corrupted
    creature at the next paint frame.
    """
    if not bitmap:
        raise ValueError(f"{name} is empty")
    width = len(bitmap[0])
    for r, row in enumerate(bitmap):
        if len(row) != width:
            raise ValueError(
                f"{name} row {r} has width {len(row)}, expected {width}"
            )
    return width, len(bitmap)


def validate_palette_keys(
    bitmap: Bitmap, palette: Mapping[str, QColor], name: str = "bitmap"
) -> None:
    """Every non-``.`` character in ``bitmap`` must have a palette entry.

    Run once at module import. The cost is a single linear pass over
    the sprite (28 × 28 = 784 cells for our small pets) so it doesn't
    show up on the render hot path.
    """
    missing: set[str] = set()
    for row in bitmap:
        for ch in row:
            if ch == "." or ch in palette:
                continue
            missing.add(ch)
    if missing:
        raise ValueError(
            f"{name} uses palette key(s) {sorted(missing)} not present in palette"
        )


# ── Rendering ──────────────────────────────────────────────────────


def draw_bitmap(
    painter: QPainter,
    bitmap: Bitmap,
    palette: Mapping[str, QColor],
    *,
    origin_x: int,
    origin_y: int,
    pixel_size: int,
    alpha: float = 1.0,
) -> None:
    """Blit ``bitmap`` as a grid of ``pixel_size`` × ``pixel_size``
    squares anchored at ``(origin_x, origin_y)``.

    The caller is responsible for turning antialiasing **off** before
    this is invoked — pixel-art relies on hard rectangle edges, and
    AA would smear them into mush.

    ``alpha`` is a final multiplier applied to every pixel's alpha
    channel; styles use this for fade-in during the hatch animation.
    """
    if alpha <= 0.0:
        return
    for r, row in enumerate(bitmap):
        y = origin_y + r * pixel_size
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            base = palette.get(ch)
            if base is None:
                # Defensive — validate_palette_keys should have caught
                # this at import time. Skip silently so a bad pixel
                # never crashes the paint loop.
                continue
            color = QColor(base)
            if alpha < 1.0:
                color.setAlphaF(max(0.0, min(1.0, color.alphaF() * alpha)))
            painter.fillRect(
                origin_x + c * pixel_size,
                y,
                pixel_size,
                pixel_size,
                color,
            )


def draw_overlay(
    painter: QPainter,
    overlay: Overlay,
    palette: Mapping[str, QColor],
    *,
    origin_x: int,
    origin_y: int,
    pixel_size: int,
    alpha: float = 1.0,
) -> None:
    """Blit a sparse ``{(col, row): char}`` overlay using the same
    pixel geometry as ``draw_bitmap``.

    Cells whose palette key is missing are skipped (same defensive
    posture as the base blitter).
    """
    if alpha <= 0.0:
        return
    for (col, row), ch in overlay.items():
        base = palette.get(ch)
        if base is None:
            continue
        color = QColor(base)
        if alpha < 1.0:
            color.setAlphaF(max(0.0, min(1.0, color.alphaF() * alpha)))
        painter.fillRect(
            origin_x + col * pixel_size,
            origin_y + row * pixel_size,
            pixel_size,
            pixel_size,
            color,
        )


def draw_overlays(
    painter: QPainter,
    overlays: Iterable[Overlay],
    palette: Mapping[str, QColor],
    *,
    origin_x: int,
    origin_y: int,
    pixel_size: int,
    alpha: float = 1.0,
) -> None:
    """Convenience: blit a sequence of overlays in order (later
    overlays paint over earlier ones, just like layers in an art
    program).
    """
    for overlay in overlays:
        draw_overlay(
            painter, overlay, palette,
            origin_x=origin_x, origin_y=origin_y,
            pixel_size=pixel_size, alpha=alpha,
        )


# ── Test helper ────────────────────────────────────────────────────


def palette_keys_used(bitmap: Bitmap) -> List[str]:
    """Return the sorted unique non-transparent characters used in a
    bitmap. Handy for tests that want to assert a sprite uses exactly
    the colors its palette advertises.
    """
    used: set[str] = set()
    for row in bitmap:
        for ch in row:
            if ch != ".":
                used.add(ch)
    return sorted(used)
