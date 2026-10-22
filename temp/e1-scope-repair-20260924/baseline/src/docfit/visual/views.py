"""Image composition helpers for visual evidence views."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from docfit.tools.images import image_metadata
from docfit.tools.runtime import JsonObject, ToolFailure


def contact_sheet(pages: list[tuple[int, Path]], output: Path, *, width: int = 1600) -> JsonObject:
    if not pages:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="contact_sheet_has_no_pages",
            message="The contact sheet request selected no pages.",
        )
    columns = min(4, max(1, math.ceil(math.sqrt(len(pages)))))
    tile_width = width // columns
    thumbnails: list[tuple[int, Image.Image]] = []
    for number, path in pages:
        with Image.open(path) as source:
            converted = source.convert("RGB")
            converted.thumbnail((tile_width - 24, int((tile_width - 24) * 1.45)))
            thumbnails.append((number, converted.copy()))
    tile_height = max(image.height for _, image in thumbnails) + 48
    rows = math.ceil(len(thumbnails) / columns)
    canvas = Image.new("RGB", (width, rows * tile_height), "#d7d7d7")
    draw = ImageDraw.Draw(canvas)
    for index, (number, thumbnail) in enumerate(thumbnails):
        column = index % columns
        row = index // columns
        x = column * tile_width + (tile_width - thumbnail.width) // 2
        y = row * tile_height + 28
        canvas.paste(thumbnail, (x, y))
        draw.text((column * tile_width + 8, row * tile_height + 6), f"Page {number}", fill="black")
    canvas.save(output, format="PNG", optimize=True)
    metadata = image_metadata(output)
    return {
        "pages": [number for number, _ in pages],
        "pixel_size": [metadata["width"], metadata["height"]],
    }


def comparison(baseline: Path, current: Path, output: Path) -> JsonObject:
    with Image.open(baseline) as baseline_image, Image.open(current) as current_image:
        first = baseline_image.convert("RGB")
        second = current_image.convert("RGB")
        width = max(first.width, second.width)
        height = max(first.height, second.height)
        first_canvas = Image.new("RGB", (width, height), "white")
        second_canvas = Image.new("RGB", (width, height), "white")
        first_canvas.paste(first, (0, 0))
        second_canvas.paste(second, (0, 0))
        difference = ImageChops.difference(first_canvas, second_canvas)
        canvas = Image.new("RGB", (width * 3, height), "white")
        canvas.paste(first_canvas, (0, 0))
        canvas.paste(second_canvas, (width, 0))
        canvas.paste(difference, (width * 2, 0))
        canvas.save(output, format="PNG", optimize=True)
    metadata = image_metadata(output)
    return {
        "view": "baseline_current_difference",
        "pixel_size": [metadata["width"], metadata["height"]],
    }
