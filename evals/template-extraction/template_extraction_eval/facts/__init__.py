"""Single public fact-analysis entry used for both Actual and Gold DOCX files."""

from __future__ import annotations

from pathlib import Path

from ..models import DocumentFacts
from .content import analyze_content
from .effective_style import EffectiveStyleAnalyzer
from .objects import analyze_objects
from .reader import DocxPackage, PackageValidationError, read_docx
from .structure import analyze_structure


def analyze_docx(path: Path) -> DocumentFacts:
    package = read_docx(path)
    style_analyzer = EffectiveStyleAnalyzer(package)
    paragraphs, controls = analyze_content(package, style_analyzer)
    tables = analyze_structure(package)
    objects, unsupported = analyze_objects(package)
    return DocumentFacts(
        document_sha256=package.document_sha256,
        parts=tuple(sorted(package.parts)),
        relationships=package.relationships,
        paragraphs=paragraphs,
        controls=controls,
        tables=tables,
        objects=objects,
        unsupported=unsupported,
    )


__all__ = [
    "DocxPackage",
    "PackageValidationError",
    "analyze_docx",
    "read_docx",
]

