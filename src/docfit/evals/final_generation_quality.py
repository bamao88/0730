"""Gold comparison helpers for final-generation quality evaluation."""

from __future__ import annotations

import re
import shutil
import zipfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from PIL import Image, ImageChops, ImageStat

from docfit.tools.images import compare_pages, pdf_page_count, pdf_to_png_pages
from docfit.tools.runtime import JsonObject, ToolFailure, atomic_write_json, sha256_file
from docfit.visual.renderer import LibreOfficeRenderer

FINAL_GENERATION_QUALITY_REPORT_SCHEMA_VERSION = (
    "docfit-final-generation-quality-report/v1"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_RESIDUE_PATTERNS = (
    ("toc_placeholder", re.compile(r"【[^】]+】|第X章")),
    ("template_instruction", re.compile(r"四号|小四号|3-5个")),
)


@dataclass(frozen=True, slots=True)
class _DocxSnapshot:
    sha256: str
    paragraphs: list[str]
    full_text: str
    tables: int
    drawings: int
    pict: int
    media_sha256: list[str]
    part_count: int
    paragraph_style_counts: dict[str, int]
    residue: list[JsonObject]


def run_final_generation_quality_compare(
    *,
    actual_docx: Path,
    gold_docx: Path,
    output_directory: Path,
    thresholds: Mapping[str, Any] | None = None,
    actual_pdf: Path | None = None,
) -> JsonObject:
    """Compare one generated DOCX with a gold DOCX and write repeatable evidence."""

    actual = actual_docx.expanduser().resolve(strict=True)
    gold = gold_docx.expanduser().resolve(strict=True)
    output = output_directory.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="quality_output_not_empty",
            message="The quality comparison output directory must be absent or empty.",
        )
    output.mkdir(parents=True, exist_ok=True)

    actual_snapshot = _snapshot(actual)
    gold_snapshot = _snapshot(gold)
    text = _text_comparison(gold_snapshot.paragraphs, actual_snapshot.paragraphs)
    media = _media_comparison(gold_snapshot, actual_snapshot)
    structure = _structure_comparison(gold_snapshot, actual_snapshot)
    visual = _visual_comparison(
        actual_docx=actual,
        gold_docx=gold,
        output_directory=output / "visual",
        actual_pdf=actual_pdf,
    )
    threshold_failures = _threshold_failures(
        thresholds or {},
        text=text,
        media=media,
        structure=structure,
        visual=visual,
        actual_snapshot=actual_snapshot,
        gold_snapshot=gold_snapshot,
    )
    report: JsonObject = {
        "schema_version": FINAL_GENERATION_QUALITY_REPORT_SCHEMA_VERSION,
        "status": "PASS" if not threshold_failures else "FAIL",
        "actual_docx": str(actual),
        "gold_docx": str(gold),
        "actual": _snapshot_summary(actual_snapshot),
        "gold": _snapshot_summary(gold_snapshot),
        "text": text,
        "structure": structure,
        "media": media,
        "visual": visual,
        "thresholds": dict(thresholds or {}),
        "threshold_failures": threshold_failures,
        "json_report": str(output / "quality-report.json"),
        "markdown_report": str(output / "quality-report.md"),
    }
    atomic_write_json(output / "quality-report.json", report)
    _write_markdown(output / "quality-report.md", report)
    return report


def _snapshot(path: Path) -> _DocxSnapshot:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            document = ET.fromstring(archive.read("word/document.xml"))
            paragraphs: list[str] = []
            style_counts: Counter[str] = Counter()
            for paragraph in document.iter(_q("p")):
                text = _normalize_text(_element_text(paragraph))
                if not text:
                    continue
                paragraphs.append(text)
                style_counts[_paragraph_style(paragraph) or "<none>"] += 1
            media_sha256 = [
                _sha256_bytes(archive.read(name))
                for name in sorted(names)
                if name.startswith("word/media/")
            ]
            residue = _residue(paragraphs)
            return _DocxSnapshot(
                sha256=sha256_file(path),
                paragraphs=paragraphs,
                full_text="\n".join(paragraphs),
                tables=sum(1 for _ in document.iter(_q("tbl"))),
                drawings=sum(1 for _ in document.iter(_q("drawing"))),
                pict=sum(1 for _ in document.iter(_q("pict"))),
                media_sha256=media_sha256,
                part_count=len(names),
                paragraph_style_counts=dict(sorted(style_counts.items())),
                residue=residue,
            )
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="quality_docx_unreadable",
            message="A quality comparison DOCX cannot be read.",
        ) from error


def _text_comparison(gold: list[str], actual: list[str]) -> JsonObject:
    full_text_similarity = SequenceMatcher(None, "\n".join(gold), "\n".join(actual)).ratio()
    paragraph_matcher = SequenceMatcher(None, gold, actual, autojunk=False)
    hunks: list[JsonObject] = []
    for tag, gold_start, gold_end, actual_start, actual_end in paragraph_matcher.get_opcodes():
        if tag == "equal":
            continue
        hunks.append(
            {
                "tag": tag,
                "gold_range": [gold_start, gold_end],
                "actual_range": [actual_start, actual_end],
                "gold_sample": gold[gold_start : min(gold_end, gold_start + 3)],
                "actual_sample": actual[actual_start : min(actual_end, actual_start + 3)],
            }
        )
    return {
        "full_text_similarity": round(full_text_similarity, 6),
        "paragraph_sequence_similarity": round(paragraph_matcher.ratio(), 6),
        "paragraph_change_hunk_count": len(hunks),
        "diff_hunks_sample": hunks[:20],
    }


def _media_comparison(gold: _DocxSnapshot, actual: _DocxSnapshot) -> JsonObject:
    gold_media = set(gold.media_sha256)
    actual_media = set(actual.media_sha256)
    return {
        "gold_media_count": len(gold.media_sha256),
        "actual_media_count": len(actual.media_sha256),
        "common_media_count": len(gold_media & actual_media),
        "gold_only_media_count": len(gold_media - actual_media),
        "actual_only_media_count": len(actual_media - gold_media),
    }


def _structure_comparison(gold: _DocxSnapshot, actual: _DocxSnapshot) -> JsonObject:
    return {
        "paragraph_count_delta": len(actual.paragraphs) - len(gold.paragraphs),
        "text_char_count_delta": len(actual.full_text) - len(gold.full_text),
        "table_count_delta": actual.tables - gold.tables,
        "drawing_count_delta": actual.drawings - gold.drawings,
        "pict_count_delta": actual.pict - gold.pict,
        "part_count_delta": actual.part_count - gold.part_count,
        "actual_residue_count": len(actual.residue),
        "actual_residue_sample": actual.residue[:20],
        "paragraph_style_counts_match": (
            actual.paragraph_style_counts == gold.paragraph_style_counts
        ),
    }


def _visual_comparison(
    *,
    actual_docx: Path,
    gold_docx: Path,
    output_directory: Path,
    actual_pdf: Path | None,
) -> JsonObject:
    renders = output_directory / "renders"
    pages = output_directory / "pages"
    diffs = output_directory / "diffs"
    renders.mkdir(parents=True, exist_ok=True)
    actual_render = renders / "actual.pdf"
    gold_render = renders / "gold.pdf"
    if actual_pdf is not None and actual_pdf.is_file():
        shutil.copy2(actual_pdf, actual_render)
    else:
        LibreOfficeRenderer().render(actual_docx, actual_render)
    LibreOfficeRenderer().render(gold_docx, gold_render)

    actual_page_count = pdf_page_count(actual_render)
    gold_page_count = pdf_page_count(gold_render)
    actual_pages = pdf_to_png_pages(actual_render, pages / "actual", dpi=72)
    gold_pages = pdf_to_png_pages(gold_render, pages / "gold", dpi=72)
    compared = min(actual_page_count, gold_page_count)
    page_results: list[JsonObject] = []
    for index in range(compared):
        page = index + 1
        page_results.append(_compare_page(gold_pages[index], actual_pages[index], page))
    top_pages = sorted(
        page_results,
        key=lambda item: float(item.get("changed_pixel_ratio", 0.0)),
        reverse=True,
    )[:4]
    diff_images: list[str] = []
    for item in top_pages:
        if item.get("comparable") is not True:
            continue
        page = int(item["page"])
        output = diffs / f"page-{page:04d}.png"
        compare_pages(gold_pages[page - 1], actual_pages[page - 1], output)
        diff_images.append(str(output))
    changed = [
        float(item["changed_pixel_ratio"])
        for item in page_results
        if item.get("comparable") is True
    ]
    return {
        "renderer": "libreoffice",
        "raster_dpi": 72,
        "actual_pdf": str(actual_render),
        "gold_pdf": str(gold_render),
        "actual_page_count": actual_page_count,
        "gold_page_count": gold_page_count,
        "page_count_delta": actual_page_count - gold_page_count,
        "compared_page_count": compared,
        "comparable_page_count": len(changed),
        "mean_changed_pixel_ratio": round(sum(changed) / len(changed), 6) if changed else None,
        "max_changed_pixel_ratio": round(max(changed), 6) if changed else None,
        "top_changed_pages": top_pages,
        "diff_images": diff_images,
    }


def _compare_page(gold_page: Path, actual_page: Path, page: int) -> JsonObject:
    with Image.open(gold_page) as gold_image, Image.open(actual_page) as actual_image:
        gold = gold_image.convert("RGB")
        actual = actual_image.convert("RGB")
        if gold.size != actual.size:
            return {
                "page": page,
                "comparable": False,
                "gold_pixel_size": list(gold.size),
                "actual_pixel_size": list(actual.size),
            }
        diff = ImageChops.difference(gold, actual)
        mask = diff.convert("L").point(lambda value: 255 if value > 8 else 0)
        histogram = mask.histogram()
        changed = histogram[255]
        total = gold.width * gold.height
        stat = ImageStat.Stat(diff)
        mean_delta = sum(float(value) for value in stat.mean) / (3 * 255)
        return {
            "page": page,
            "comparable": True,
            "pixel_size": list(gold.size),
            "changed_pixel_ratio": round(changed / total, 6),
            "mean_abs_delta_ratio": round(mean_delta, 6),
        }


def _threshold_failures(
    thresholds: Mapping[str, Any],
    *,
    text: JsonObject,
    media: JsonObject,
    structure: JsonObject,
    visual: JsonObject,
    actual_snapshot: _DocxSnapshot,
    gold_snapshot: _DocxSnapshot,
) -> list[JsonObject]:
    failures: list[JsonObject] = []

    def minimum(name: str, actual: Any) -> None:
        expected = thresholds.get(name)
        if (
            isinstance(expected, int | float)
            and isinstance(actual, int | float)
            and float(actual) < float(expected)
        ):
            failures.append({"metric": name, "expected_min": expected, "actual": actual})

    def maximum(name: str, actual: Any) -> None:
        expected = thresholds.get(name)
        if (
            isinstance(expected, int | float)
            and isinstance(actual, int | float)
            and float(actual) > float(expected)
        ):
            failures.append({"metric": name, "expected_max": expected, "actual": actual})

    minimum("min_full_text_similarity", text.get("full_text_similarity"))
    minimum("min_paragraph_sequence_similarity", text.get("paragraph_sequence_similarity"))
    maximum("max_page_count_delta_abs", abs(int(visual.get("page_count_delta", 0))))
    maximum(
        "max_media_delta",
        int(media.get("gold_only_media_count", 0)) + int(media.get("actual_only_media_count", 0)),
    )
    maximum("max_placeholder_residue_count", len(actual_snapshot.residue))
    maximum(
        "max_visual_changed_pixel_ratio_mean",
        visual.get("mean_changed_pixel_ratio"),
    )
    maximum(
        "max_visual_changed_pixel_ratio_page",
        visual.get("max_changed_pixel_ratio"),
    )
    if (
        thresholds.get("require_exact_sha256_match") is True
        and actual_snapshot.sha256 != gold_snapshot.sha256
    ):
        failures.append(
            {
                "metric": "require_exact_sha256_match",
                "expected": True,
                "actual": False,
            }
        )
    if (
        thresholds.get("require_paragraph_style_counts_match") is True
        and structure.get("paragraph_style_counts_match") is not True
    ):
        failures.append(
            {
                "metric": "require_paragraph_style_counts_match",
                "expected": True,
                "actual": False,
            }
        )
    return failures


def _snapshot_summary(snapshot: _DocxSnapshot) -> JsonObject:
    return {
        "sha256": snapshot.sha256,
        "paragraph_count": len(snapshot.paragraphs),
        "text_char_count": len(snapshot.full_text),
        "table_count": snapshot.tables,
        "drawing_count": snapshot.drawings,
        "legacy_pict_count": snapshot.pict,
        "media_count": len(snapshot.media_sha256),
        "part_count": snapshot.part_count,
        "paragraph_style_counts": snapshot.paragraph_style_counts,
        "residue_count": len(snapshot.residue),
    }


def _write_markdown(path: Path, report: JsonObject) -> None:
    lines = [
        "# Final-generation Quality Compare",
        "",
        f"Status: {report['status']}",
        "",
        "## Inputs",
        "",
        f"- Actual: `{report['actual_docx']}`",
        f"- Gold: `{report['gold_docx']}`",
        "",
        "## Metrics",
        "",
        f"- Text similarity: {report['text']['full_text_similarity']}",
        f"- Paragraph sequence similarity: {report['text']['paragraph_sequence_similarity']}",
        f"- Paragraph delta: {report['structure']['paragraph_count_delta']}",
        f"- Page delta: {report['visual']['page_count_delta']}",
        f"- Media delta: "
        f"{report['media']['gold_only_media_count']} gold-only, "
        f"{report['media']['actual_only_media_count']} actual-only",
        f"- Placeholder residue count: {report['structure']['actual_residue_count']}",
        f"- Mean visual changed pixel ratio: {report['visual']['mean_changed_pixel_ratio']}",
        f"- Max visual changed pixel ratio: {report['visual']['max_changed_pixel_ratio']}",
        "",
        "## Threshold Failures",
        "",
    ]
    failures = report.get("threshold_failures")
    if isinstance(failures, list) and failures:
        lines.extend(f"- `{item.get('metric')}`: {item}" for item in failures)
    else:
        lines.append("- None")
    lines.extend(["", "## Diff Samples", ""])
    for item in report["text"]["diff_hunks_sample"][:8]:
        lines.append(
            f"- {item['tag']} gold={item['gold_range']} actual={item['actual_range']}"
        )
        gold_sample = " / ".join(str(value) for value in item.get("gold_sample", []))
        actual_sample = " / ".join(str(value) for value in item.get("actual_sample", []))
        if gold_sample:
            lines.append(f"  Gold: {gold_sample}")
        if actual_sample:
            lines.append(f"  Actual: {actual_sample}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _residue(paragraphs: list[str]) -> list[JsonObject]:
    result: list[JsonObject] = []
    for index, paragraph in enumerate(paragraphs):
        matches = [
            code
            for code, pattern in _RESIDUE_PATTERNS
            if pattern.search(paragraph)
        ]
        if matches:
            result.append(
                {
                    "paragraph_index": index,
                    "codes": matches,
                    "text": paragraph[:240],
                }
            )
    return result


def _paragraph_style(paragraph: ET.Element) -> str | None:
    style = paragraph.find(f"{_q('pPr')}/{_q('pStyle')}")
    return style.get(_q("val")) if style is not None else None


def _element_text(element: ET.Element) -> str:
    values: list[str] = []
    for node in element.iter():
        if node.tag in {_q("t"), _q("delText")}:
            values.append(node.text or "")
        elif node.tag == _q("tab"):
            values.append("\t")
        elif node.tag == _q("br"):
            values.append("\n")
    return "".join(values)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def _sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()
