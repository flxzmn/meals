"""Draw icon.png (512 x 512): a plate with fork and knife. Standard library only.

Usage: python scripts/make_icon.py
"""

import math
import struct
import zlib
from pathlib import Path

SIZE = 512
SAMPLES = 3  # samples per pixel axis for smooth edges
OUTPUT = Path(__file__).resolve().parent.parent / "icon.png"

BACKGROUND = (20, 92, 84)
PLATE = (250, 245, 232)
RIM = (233, 150, 62)
CUTLERY = (20, 92, 84)


def box(x, y, left, top, right, bottom, radius=0.0):
    """Signed distance to a rounded rectangle; negative inside."""
    dx = max(left + radius - x, x - right + radius, 0.0)
    dy = max(top + radius - y, y - bottom + radius, 0.0)
    inner = min(max(left + radius - x, x - right + radius, top + radius - y, y - bottom + radius), 0.0)
    return math.hypot(dx, dy) + inner - radius


def circle(x, y, cx, cy, radius):
    return math.hypot(x - cx, y - cy) - radius


def is_cutlery(x, y):
    # Fork: three tines, head, handle.
    for left in (172, 196, 220):
        if box(x, y, left, 140, left + 12, 235, 6) < 0:
            return True
    if box(x, y, 172, 215, 232, 262, 16) < 0 or box(x, y, 192, 240, 212, 372, 10) < 0:
        return True
    # Knife: blade with a rounded back, handle.
    if box(x, y, 292, 140, 340, 262, 24) < 0 and x >= 300:
        return True
    return box(x, y, 300, 240, 322, 372, 10) < 0


def color_at(x, y):
    if box(x, y, 0, 0, SIZE, SIZE, 96) > 0:
        return (0, 0, 0, 0)
    distance = circle(x, y, 256, 256, 196)
    if distance > 0:
        return (*BACKGROUND, 255)
    if distance > -12:
        return (*RIM, 255)
    return (*(CUTLERY if is_cutlery(x, y) else PLATE), 255)


def pixel(column, row):
    step = 1 / SAMPLES
    total = [0, 0, 0, 0]
    for i in range(SAMPLES):
        for j in range(SAMPLES):
            r, g, b, a = color_at(column + (i + 0.5) * step, row + (j + 0.5) * step)
            total[0] += r * a
            total[1] += g * a
            total[2] += b * a
            total[3] += a
    if not total[3]:
        return b"\0\0\0\0"
    return bytes((round(total[0] / total[3]), round(total[1] / total[3]), round(total[2] / total[3]), total[3] // SAMPLES ** 2))


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def main() -> None:
    rows = b"".join(b"\0" + b"".join(pixel(column, row) for column in range(SIZE)) for row in range(SIZE))
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    OUTPUT.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
