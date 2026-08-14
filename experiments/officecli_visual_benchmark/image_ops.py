"""Image normalization and comparison sheets for OfficeCLI benchmark evidence."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def normalize_officecli_page(source: Path, target: Path) -> tuple[int, int, int, int]:
    """Crop the page from OfficeCLI's fixed browser viewport for metric fairness."""

    with Image.open(source) as image:
        rgb = image.convert("RGB")
        background = rgb.getpixel((0, 0))
        delta = ImageChops.difference(
            rgb, Image.new("RGB", rgb.size, background)
        ).convert("L")
        bbox = delta.point(lambda value: 255 if value > 6 else 0).getbbox()
        if bbox is None:
            bbox = (0, 0, rgb.width, rgb.height)
        left, top, right, bottom = bbox
        if right - left < rgb.width * 0.35 or bottom - top < rgb.height * 0.65:
            bbox = (0, 0, rgb.width, rgb.height)
        target.parent.mkdir(parents=True, exist_ok=True)
        rgb.crop(bbox).save(target, format="PNG", optimize=True)
        return bbox


def _fit_page(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        return ImageOps.contain(source.convert("RGB"), size, Image.Resampling.LANCZOS)


def create_triptych(word: Path, officecli: Path, libreoffice: Path, target: Path) -> None:
    width, height, label_height = 420, 594, 42
    sources = (word, officecli, libreoffice)
    labels = ("Word reference", "OfficeCLI HTML", "LibreOffice + fonts")
    canvas = Image.new("RGB", (width * 3, height + label_height), "#dddddd")
    draw = ImageDraw.Draw(canvas)
    for index, (label, source) in enumerate(zip(labels, sources, strict=True)):
        panel = _fit_page(source, (width - 20, height - 20))
        x = index * width + (width - panel.width) // 2
        y = label_height + (height - panel.height) // 2
        canvas.paste(panel, (x, y))
        draw.text((index * width + 12, 14), label, fill="black")
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)


def _contact_panel(paths: list[Path], label: str, width: int = 560) -> Image.Image:
    columns, gap, top = 4, 8, 32
    tile_width = (width - gap * (columns + 1)) // columns
    tile_height = round(tile_width * 1.414)
    rows = (len(paths) + columns - 1) // columns
    panel = Image.new(
        "RGB", (width, top + gap + rows * (tile_height + 24 + gap)), "#d6d6d6"
    )
    draw = ImageDraw.Draw(panel)
    draw.text((10, 10), f"{label} — {len(paths)} pages", fill="black")
    for index, source in enumerate(paths):
        thumbnail = _fit_page(source, (tile_width, tile_height))
        column, row = index % columns, index // columns
        x = gap + column * (tile_width + gap) + (tile_width - thumbnail.width) // 2
        y = top + gap + row * (tile_height + 24 + gap)
        panel.paste(thumbnail, (x, y))
        label_position = (gap + column * (tile_width + gap), y + tile_height + 5)
        draw.text(label_position, str(index + 1), fill="black")
    return panel


def create_document_overview(
    word: list[Path], officecli: list[Path], libreoffice: list[Path], target: Path
) -> None:
    panels = [
        _contact_panel(word, "Word reference"),
        _contact_panel(officecli, "OfficeCLI HTML"),
        _contact_panel(libreoffice, "LibreOffice + fonts"),
    ]
    canvas_size = (
        sum(panel.width for panel in panels),
        max(panel.height for panel in panels),
    )
    canvas = Image.new("RGB", canvas_size, "white")
    x = 0
    for panel in panels:
        canvas.paste(panel, (x, 0))
        x += panel.width
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)
