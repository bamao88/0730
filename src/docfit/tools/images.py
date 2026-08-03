"""Local image derivation for render and visual-evidence Tools."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REVIEW_IMAGES = 12


def _run_binary(arguments: list[str], *, timeout_seconds: int = 120) -> None:
    try:
        completed = subprocess.run(
            arguments,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="image_derivation_failed",
            message="A required local PDF or image derivation command failed.",
            retryable=isinstance(error, subprocess.TimeoutExpired),
        ) from error
    if completed.returncode != 0:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="image_derivation_failed",
            message="A required local PDF or image derivation command returned an error.",
        )


def pdf_page_count(pdf: Path) -> int:
    executable = shutil.which("pdfinfo")
    if executable is None:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="pdfinfo_not_found",
            message="pdfinfo is required to derive complete PDF page evidence.",
        )
    try:
        completed = subprocess.run(
            [executable, str(pdf)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="pdfinfo_failed",
            message="The converted PDF could not be inspected locally.",
        ) from error
    if completed.returncode != 0:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="converted_pdf_unreadable",
            message="The conversion provider produced a PDF that pdfinfo cannot read.",
        )
    for line in completed.stdout.splitlines():
        if line.startswith("Pages:"):
            value = line.partition(":")[2].strip()
            if value.isdigit() and int(value) > 0:
                return int(value)
    raise ToolFailure(
        status="error",
        origin="postcondition",
        code="converted_pdf_page_count_missing",
        message="The converted PDF has no readable positive page count.",
    )


def pdf_to_png_pages(pdf: Path, pages_directory: Path, *, dpi: int = 144) -> list[Path]:
    executable = shutil.which("pdftoppm")
    if executable is None:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="pdftoppm_not_found",
            message="pdftoppm is required to derive complete PDF page evidence.",
        )
    expected_count = pdf_page_count(pdf)
    pages_directory.mkdir(parents=True, exist_ok=True)
    prefix = pages_directory / "page"
    _run_binary([executable, "-png", "-r", str(dpi), str(pdf), str(prefix)])
    pages = sorted(pages_directory.glob("page-*.png"))
    if len(pages) != expected_count:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="converted_page_derivation_incomplete",
            message="The number of derived page images does not match the converted PDF.",
        )
    for page in pages:
        verify_png(page)
    return pages


def verify_png(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, ValueError) as error:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="invalid_page_image",
            message="A render backend produced an unreadable page image.",
        ) from error
    if width <= 0 or height <= 0:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="empty_page_image",
            message="A render backend produced an empty page image.",
        )
    return width, height


def image_metadata(path: Path) -> JsonObject:
    width, height = verify_png(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
    }


def create_contact_sheet(
    pages: list[Path],
    output: Path,
    *,
    max_pages: int = 20,
    width: int = 1600,
) -> JsonObject:
    selected = pages[:max_pages]
    if not selected:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="render_has_no_pages",
            message="No page images exist for a contact sheet.",
        )
    columns = min(4, max(1, math.ceil(math.sqrt(len(selected)))))
    tile_width = width // columns
    thumbnails: list[Image.Image] = []
    for page in selected:
        with Image.open(page) as source:
            converted = source.convert("RGB")
            converted.thumbnail((tile_width - 24, int((tile_width - 24) * 1.45)))
            thumbnails.append(converted.copy())
    tile_height = max(image.height for image in thumbnails) + 48
    rows = math.ceil(len(thumbnails) / columns)
    canvas = Image.new("RGB", (width, rows * tile_height), "#d7d7d7")
    draw = ImageDraw.Draw(canvas)
    for index, thumbnail in enumerate(thumbnails):
        column = index % columns
        row = index // columns
        x = column * tile_width + (tile_width - thumbnail.width) // 2
        y = row * tile_height + 28
        canvas.paste(thumbnail, (x, y))
        draw.text(
            (column * tile_width + 8, row * tile_height + 6), f"Page {index + 1}", fill="black"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
    return image_metadata(output)


def crop_page(page: Path, bbox: list[int], output: Path) -> JsonObject:
    if len(bbox) != 4 or any(not isinstance(value, int) for value in bbox):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_crop_bbox",
            message="A crop bbox must contain four integer pixel coordinates.",
        )
    with Image.open(page) as source:
        width, height = source.size
        left, top, right, bottom = bbox
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="crop_out_of_bounds",
                message="A crop bbox lies outside the selected page.",
            )
        cropped = source.convert("RGB").crop((left, top, right, bottom))
        output.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(output, format="PNG", optimize=True)
    return image_metadata(output)


def compare_pages(baseline: Path, current: Path, output: Path) -> JsonObject:
    with Image.open(baseline) as baseline_image, Image.open(current) as current_image:
        first = baseline_image.convert("RGB")
        second = current_image.convert("RGB")
        if first.size != second.size:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="incomparable_page_dimensions",
                message="Compare requires equal page pixel dimensions.",
            )
        difference = ImageChops.difference(first, second)
        canvas = Image.new("RGB", (first.width * 3, first.height), "white")
        canvas.paste(first, (0, 0))
        canvas.paste(second, (first.width, 0))
        canvas.paste(difference, (first.width * 2, 0))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="PNG", optimize=True)
    metadata = image_metadata(output)
    metadata["view"] = "baseline_current_difference"
    return metadata


def font_environment_fingerprint() -> JsonObject:
    roots = (
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        Path("/usr/share/fonts"),
    )
    records: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix.casefold() not in {".ttf", ".ttc", ".otf"}:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            records.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
    return {
        "fingerprint": sha256_json(records),
        "font_file_count": len(records),
        "substitutions": [],
        "source": "local_font_inventory_metadata",
    }


def ensure_review_budget(paths: list[Path]) -> None:
    if len(paths) > MAX_REVIEW_IMAGES:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="too_many_review_images",
            message=f"One visual-review call may return at most {MAX_REVIEW_IMAGES} images.",
        )
    total = sum(path.stat().st_size for path in paths)
    if total > MAX_IMAGE_BYTES:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="review_image_budget_exceeded",
            message="The requested visual evidence exceeds the per-call byte limit.",
        )


def poppler_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for name in ("pdftoppm", "pdfinfo"):
        executable = shutil.which(name)
        if executable is None:
            result[name] = None
            continue
        try:
            completed = subprocess.run(
                [executable, "-v"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=dict(os.environ),
            )
        except (OSError, subprocess.TimeoutExpired):
            result[name] = None
            continue
        output = (completed.stderr or completed.stdout).splitlines()
        result[name] = output[0].strip() if output else None
    return result
