"""External rendering ports used by the template domain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from docfit.tools.adobe import AdobePdfServicesAdapter
from docfit.tools.images import pdf_to_png_pages
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import JsonObject, ToolFailure


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    pages: tuple[Path, ...]
    provider: JsonObject
    pdf: Path | None = None


class TemplateRenderer(Protocol):
    def render(
        self,
        document: Path,
        *,
        visual_level: str,
        output: Path,
    ) -> RenderedDocument: ...


class DefaultTemplateRenderer:
    """Fixed routing: OfficeCLI for quick evidence, Adobe for candidate verification."""

    def __init__(
        self,
        *,
        office: OfficeCliAdapter | None = None,
        adobe: AdobePdfServicesAdapter | None = None,
    ) -> None:
        self._office = office
        self._adobe = adobe

    @property
    def office(self) -> OfficeCliAdapter:
        if self._office is None:
            self._office = OfficeCliAdapter()
        return self._office

    @property
    def adobe(self) -> AdobePdfServicesAdapter:
        if self._adobe is None:
            self._adobe = AdobePdfServicesAdapter()
        return self._adobe

    def render(
        self,
        document: Path,
        *,
        visual_level: str,
        output: Path,
    ) -> RenderedDocument:
        pages_directory = output / "pages"
        pages_directory.mkdir(parents=True)
        if visual_level == "quick":
            html = output / "document.html"
            self.office.html(document, html)
            page_count = len(
                re.findall(r"\bdata-page(?:=|\b)", html.read_text(errors="replace"))
            ) or 1
            if page_count > 500:
                raise ToolFailure(
                    status="error",
                    origin="renderer",
                    code="render_page_limit_exceeded",
                    message="The quick render exceeds the configured page limit.",
                )
            pages: list[Path] = []
            for number in range(1, page_count + 1):
                page = pages_directory / f"page-{number:04d}.png"
                self.office.screenshot(document, page=number, output=page)
                pages.append(page)
            return RenderedDocument(tuple(pages), self.office.evidence())
        if visual_level == "candidate_verification":
            pdf = output / "document.pdf"
            self.adobe.export_pdf(document, pdf)
            candidate_pages = tuple(pdf_to_png_pages(pdf, pages_directory, dpi=144))
            return RenderedDocument(candidate_pages, self.adobe.evidence(), pdf)
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_visual_level",
            message="The requested visual evidence level is unsupported.",
        )
