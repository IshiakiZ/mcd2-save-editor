"""Rounded, glassy shapes for Simple mode's buttons, tabs, panels and fields.

Everything is drawn here, pixel by pixel, into small PNG pictures with see-through edges (no picture files, and
nothing but the standard library), and ttk fits each one to its widget: the corners keep their shape and the
middle fills in. A shape is a rounded rectangle with a fill, a bright rim along the top, a hairline round it and
a soft shadow under it, which is what makes a flat button read as a piece of glass. The look follows Apple's
Liquid Glass (capsules, one tinted button for the main action, glass for the controls and not for the content);
the colours stay the game's.
"""

from __future__ import annotations

import base64
import math
import struct
import zlib
from dataclasses import dataclass
from typing import Sequence

Pixel = tuple[float, float, float, float]  # red, green, blue (0 to 255) and how solid (0 to 1)
CLEAR: Pixel = (0.0, 0.0, 0.0, 0.0)


def rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


@dataclass(frozen=True)
class Shape:
    """A rounded rectangle: what it's filled with and how its edges catch the light."""

    fill: str = "#ffffff"  # the body's colour
    alpha: float = 1.0  # how solid the body is: under 1 lets what's behind it through, like glass
    radius: float = 8
    glow: float = 0.0  # white added to the top of the body, fading out over ``zone`` pixels
    shade: float = 0.0  # black added to the bottom of the body, likewise
    rim: float = 0.0  # a bright line just inside the top edge
    edge: str = "#000000"  # the hairline round the shape...
    edge_alpha: float = 0.0  # ...and how solid it is
    shadow: float = 0.0  # a soft shadow under the shape
    drop: int = 0  # how far the shadow falls, in pixels: the body stops this far short of the bottom of its box
    zone: float = 0.0  # how far the glow and the shade reach in from the edge; 0: as far as the radius
    inset: float = 0.0  # a shadow inside the top edge, for something set into the surface (a text box, a well)
    band: float = 0.0  # a strip this tall along the top, in ``band_fill``, its last two pixels darker (a panel's title)
    band_fill: str = "#ffffff"


@dataclass(frozen=True)
class Stroke:
    """A line through ``points`` (in the picture's pixels), ``width`` pixels thick with round ends."""

    points: tuple[tuple[float, float], ...]
    width: float
    color: str
    alpha: float = 1.0


def _distance(px: float, py: float, x0: float, y0: float, x1: float, y1: float, radius: float) -> float:
    """How far a point is outside a rounded rectangle (negative inside)."""
    half_x, half_y = (x1 - x0) / 2 - radius, (y1 - y0) / 2 - radius
    qx, qy = abs(px - (x0 + x1) / 2) - half_x, abs(py - (y0 + y1) / 2) - half_y
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - radius


def _to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    along = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + along * dx), py - (ay + along * dy))


def _clamp(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _over(under: Pixel, color: Sequence[float], alpha: float) -> Pixel:
    """``color`` at ``alpha`` laid over a colour that may itself be see-through."""
    if alpha <= 0.0:
        return under
    r, g, b, a = under
    out = alpha + a * (1.0 - alpha)
    keep = a * (1.0 - alpha)
    return (color[0] * alpha + r * keep) / out, (color[1] * alpha + g * keep) / out, (color[2] * alpha + b * keep) / out, out


def _shape_at(shape: Shape, px: float, py: float, width: float, height: float) -> tuple[Pixel, float]:
    """The shape's colour at a point of its own box, and how much of the shadow under it shows there."""
    bottom = height - shape.drop
    radius = min(shape.radius, width / 2, bottom / 2)
    shadow = 0.0
    if shape.shadow and shape.drop:
        beyond = _distance(px, py - shape.drop * 0.6, 0, 0, width, bottom, radius)
        soft = _clamp(1.0 - max(beyond, 0.0) / (shape.drop * 1.6))
        shadow = shape.shadow * soft * soft
    d = _distance(px, py, 0, 0, width, bottom, radius)
    inside = _clamp(0.5 - d)
    if inside <= 0.0:
        return CLEAR, shadow
    zone = shape.zone or max(radius, 4.0)
    down, up = py / zone, (bottom - py) / zone  # 0 at the edge, 1 where the light has faded out
    banded = bool(shape.band) and py < shape.band
    color: Pixel = (*rgb(shape.band_fill if banded else shape.fill), shape.alpha)
    if banded and py > shape.band - 2:
        color = _over(color, (0, 0, 0), 0.3)  # the darker line along the bottom of the title strip
    if shape.glow and down < 1.0:
        color = _over(color, (255, 255, 255), shape.glow * (1.0 - down) ** 2)
    if shape.shade and up < 1.0:
        color = _over(color, (0, 0, 0), shape.shade * (1.0 - up) ** 2)
    if shape.inset and down < 1.0:
        color = _over(color, (0, 0, 0), shape.inset * (1.0 - down) ** 2)
    ring = inside - _clamp(0.5 - (d + 1.0))  # the pixel just inside the edge
    if ring > 0.0:
        if shape.edge_alpha:
            color = _over(color, rgb(shape.edge), shape.edge_alpha * ring)
        if shape.rim and down < 1.0:
            color = _over(color, (255, 255, 255), shape.rim * ring * (1.0 - down))
    return (color[0], color[1], color[2], color[3] * inside), shadow


def render(width: int, height: int, *parts: Shape | Stroke | tuple[Shape, tuple[float, float, float, float]]) -> list[list[tuple[int, int, int, int]]]:
    """A picture ``width`` by ``height`` as rows of (red, green, blue, alpha, each 0 to 255), with ``parts`` laid
    one over the other: a shape fills the picture unless it comes with its own box (left, top, right, bottom)."""
    if len(parts) == 1 and isinstance(parts[0], Shape):
        return _render_one(width, height, parts[0])
    rows = []
    for y in range(height):
        row = []
        py = y + 0.5
        for x in range(width):
            px = x + 0.5
            pixel = CLEAR
            for part in parts:
                if isinstance(part, Stroke):
                    points = part.points
                    near = min(_to_segment(px, py, *points[i], *points[i + 1]) for i in range(len(points) - 1))
                    pixel = _over(pixel, rgb(part.color), part.alpha * _clamp(part.width / 2 + 0.5 - near))
                    continue
                shape, (x0, y0, x1, y1) = part if isinstance(part, tuple) else (part, (0, 0, width, height))
                color, shadow = _shape_at(shape, px - x0, py - y0, x1 - x0, y1 - y0)
                pixel = _over(_over(pixel, (0, 0, 0), shadow), color[:3], color[3])
            row.append((round(pixel[0]), round(pixel[1]), round(pixel[2]), round(pixel[3] * 255)))
        rows.append(row)
    return rows


def _render_one(width: int, height: int, shape: Shape) -> list[list[tuple[int, int, int, int]]]:
    """One shape filling the picture. It's the same all the way across but for its ends, and its two ends mirror
    each other, so a wide picture costs no more to draw than a narrow one: ttk has fewer pieces to lay side by
    side when the middle of a picture is big, and that's what keeps a large panel quick to draw."""
    ends = min(width // 2, math.ceil(shape.radius + shape.drop * 1.6) + 2)
    rows = []
    for y in range(height):
        py = y + 0.5

        def at(px: float) -> tuple[int, int, int, int]:
            color, shadow = _shape_at(shape, px, py, width, height)
            pixel = _over(_over(CLEAR, (0, 0, 0), shadow), color[:3], color[3])
            return round(pixel[0]), round(pixel[1]), round(pixel[2]), round(pixel[3] * 255)

        left = [at(x + 0.5) for x in range(ends)]
        middle = [at(width / 2)] * (width - 2 * ends) if width > 2 * ends else []
        rows.append(left + middle + (left[::-1] if width >= 2 * ends else left[: width - ends][::-1]))
    return rows


def png(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    """Rows of (red, green, blue, alpha) as a PNG file."""
    height, width = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(value for pixel in row for value in pixel) for row in rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def picture(width: int, height: int, *parts: Shape | Stroke | tuple[Shape, tuple[float, float, float, float]]) -> str:
    """``render`` as PNG data the way Tk takes it (``tk.PhotoImage(data=...)``)."""
    return base64.b64encode(png(render(width, height, *parts))).decode("ascii")
