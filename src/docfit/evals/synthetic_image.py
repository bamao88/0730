"""Small deterministic image used only inside synthetic Eval documents."""

from __future__ import annotations

import struct
import zlib


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def make_fixture_png() -> bytes:
    """Return a deterministic colored PNG for DOCX image-preservation fixtures."""
    width = height = 48
    rows = []
    for y in range(height):
        pixels = bytearray()
        for x in range(width):
            border = x < 4 or y < 4 or x >= width - 4 or y >= height - 4
            pixels.extend((20, 82, 180) if border else (31, 153, 93))
        rows.append(b"\x00" + bytes(pixels))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(b"".join(rows), level=9))
        + _chunk(b"IEND", b"")
    )
