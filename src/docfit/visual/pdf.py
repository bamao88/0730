"""Poppler-backed PDF metadata, text coordinates, and on-demand rasterization."""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.tools.images import image_metadata, pdf_page_count
from docfit.tools.runtime import JsonObject, ToolFailure


class PdfBackend:
    def __init__(self, *, timeout_seconds: int = 120) -> None:
        self.timeout_seconds = timeout_seconds

    def build_text_index(self, pdf: Path) -> JsonObject:
        executable = shutil.which("pdftotext")
        if executable is None:
            self._missing("pdftotext")
        assert executable is not None
        completed = self._run(
            [executable, "-bbox-layout", "-enc", "UTF-8", str(pdf), "-"],
            code="pdf_text_index_failed",
        )
        try:
            root = ET.fromstring(completed.stdout)
        except ET.ParseError as error:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="pdf_text_index_invalid",
                message="Poppler returned an unreadable PDF text coordinate index.",
            ) from error
        pages: list[JsonObject] = []
        for number, page in enumerate(
            (item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "page"),
            start=1,
        ):
            try:
                width = float(page.attrib["width"])
                height = float(page.attrib["height"])
            except (KeyError, ValueError) as error:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="pdf_page_metadata_invalid",
                    message="The converted PDF has invalid page dimensions.",
                ) from error
            words: list[JsonObject] = []
            for word in (item for item in page.iter() if item.tag.rsplit("}", 1)[-1] == "word"):
                text = "".join(word.itertext())
                if not text:
                    continue
                try:
                    bbox = [
                        float(word.attrib[key])
                        for key in ("xMin", "yMin", "xMax", "yMax")
                    ]
                except (KeyError, ValueError) as error:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="pdf_text_bbox_invalid",
                        message="The converted PDF has invalid text coordinates.",
                    ) from error
                words.append({"text": text, "bbox_pdf": bbox})
            pages.append(
                {
                    "page": number,
                    "width_pt": width,
                    "height_pt": height,
                    "text": " ".join(str(word["text"]) for word in words),
                    "words": words,
                }
            )
        expected = pdf_page_count(pdf)
        if not pages or len(pages) != expected:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="pdf_text_index_incomplete",
                message="The PDF text index does not cover every converted page.",
            )
        return {"schema_version": 2, "page_count": len(pages), "pages": pages}

    def rasterize_page(self, pdf: Path, page: int, dpi: int, output: Path) -> JsonObject:
        self._rasterize(pdf, page, dpi, output)
        metadata = image_metadata(output)
        return {
            "page": page,
            "dpi": dpi,
            "pixel_size": [metadata["width"], metadata["height"]],
        }

    def rasterize_region(
        self,
        pdf: Path,
        page: int,
        bbox_pdf: list[float],
        dpi: int,
        output: Path,
    ) -> JsonObject:
        scale = dpi / 72
        left, top, right, bottom = bbox_pdf
        x = max(0, math.floor(left * scale))
        y = max(0, math.floor(top * scale))
        width = max(1, math.ceil((right - left) * scale))
        height = max(1, math.ceil((bottom - top) * scale))
        self._rasterize(
            pdf,
            page,
            dpi,
            output,
            crop=(x, y, width, height),
        )
        metadata = image_metadata(output)
        return {
            "page": page,
            "dpi": dpi,
            "bbox_pdf": bbox_pdf,
            "pixel_size": [metadata["width"], metadata["height"]],
        }

    def _rasterize(
        self,
        pdf: Path,
        page: int,
        dpi: int,
        output: Path,
        *,
        crop: tuple[int, int, int, int] | None = None,
    ) -> None:
        executable = shutil.which("pdftoppm")
        if executable is None:
            self._missing("pdftoppm")
        assert executable is not None
        output.parent.mkdir(parents=True, exist_ok=True)
        prefix = output.with_suffix("")
        arguments = [
            executable,
            "-f",
            str(page),
            "-l",
            str(page),
            "-singlefile",
            "-png",
            "-r",
            str(dpi),
        ]
        if crop is not None:
            x, y, width, height = crop
            arguments.extend(["-x", str(x), "-y", str(y), "-W", str(width), "-H", str(height)])
        arguments.extend([str(pdf), str(prefix)])
        self._run(arguments, code="pdf_rasterization_failed")
        generated = prefix.with_suffix(".png")
        if generated != output and generated.is_file():
            generated.replace(output)
        image_metadata(output)

    def _run(self, arguments: list[str], *, code: str) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code=code,
                message="A required Poppler PDF operation failed.",
                retryable=isinstance(error, subprocess.TimeoutExpired),
            ) from error
        if completed.returncode != 0:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code=code,
                message="A required Poppler PDF operation returned an error.",
            )
        return completed

    @staticmethod
    def _missing(name: str) -> None:
        raise ToolFailure(
            status="error",
            origin="environment",
            code=f"{name}_not_found",
            message=f"{name} is required for LibreOffice visual evidence.",
        )
