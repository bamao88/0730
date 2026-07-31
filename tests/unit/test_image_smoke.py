from __future__ import annotations

import struct
import zlib

from docfit.image_smoke import make_smoke_png


def _decode_rgb_rows(png: bytes) -> tuple[int, int, bytes]:
    width, height = struct.unpack(">II", png[16:24])
    offset = 8
    compressed = bytearray()
    while offset < len(png):
        length = struct.unpack(">I", png[offset : offset + 4])[0]
        chunk_type = png[offset + 4 : offset + 8]
        payload = png[offset + 8 : offset + 8 + length]
        if chunk_type == b"IDAT":
            compressed.extend(payload)
        offset += 12 + length
    raw = zlib.decompress(compressed)
    return width, height, raw


def test_smoke_png_has_expected_dimensions_and_colors() -> None:
    png = make_smoke_png()

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, raw = _decode_rgb_rows(png)
    assert (width, height) == (520, 150)
    assert len(raw) == height * (1 + width * 3)
    assert raw[1:4] == bytes((20, 82, 180))
    assert bytes((31, 153, 93)) in raw
