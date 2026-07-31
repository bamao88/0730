"""Generate a deterministic PNG for the live M0 multimodal smoke."""

from __future__ import annotations

import struct
import zlib

SMOKE_MARKER = "DOCFIT-M0-IMAGE-SMOKE"
SMOKE_BORDER_COLOR = "BLUE"

_FONT: dict[str, tuple[str, ...]] = {
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
}


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    body = chunk_type + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def make_smoke_png() -> bytes:
    """Return a PNG whose marker must be read from the image, not tool text."""
    width, height = 520, 150
    white = (250, 252, 255)
    blue = (20, 82, 180)
    dark = (18, 30, 54)
    green = (31, 153, 93)
    pixels = [list(white) for _ in range(width * height)]

    def paint(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            pixels[y * width + x] = list(color)

    border = 8
    for y in range(height):
        for x in range(width):
            if x < border or x >= width - border or y < border or y >= height - border:
                paint(x, y, blue)

    scale = 3
    text_width = len(SMOKE_MARKER) * 6 * scale - scale
    start_x = (width - text_width) // 2
    start_y = 48
    for char_index, char in enumerate(SMOKE_MARKER):
        glyph = _FONT[char]
        glyph_x = start_x + char_index * 6 * scale
        for row_index, row in enumerate(glyph):
            for column_index, bit in enumerate(row):
                if bit == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            paint(
                                glyph_x + column_index * scale + dx,
                                start_y + row_index * scale + dy,
                                dark,
                            )

    for y in range(104, 126):
        for x in range(220, 300):
            if (x - 260) ** 2 + (y - 115) ** 2 <= 11**2:
                paint(x, y, green)

    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in (
        pixels[y * width : (y + 1) * width] for y in range(height)
    ))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )
