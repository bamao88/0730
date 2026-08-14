"""Compare OfficeCLI HTML screenshots with Word and LibreOffice page evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.libreoffice_compat.benchmark_api import load_benchmark_api
from experiments.libreoffice_compat.manifest import load_manifest
from experiments.libreoffice_compat.visual import horizontal_line_geometry
from experiments.officecli_visual_benchmark.image_ops import (
    create_document_overview,
    create_triptych,
    image_size,
    normalize_officecli_page,
)


def _pages(path: Path, natural_key: Any) -> list[Path]:
    values = sorted(path.glob("page-*.png"), key=natural_key)
    if not values:
        raise FileNotFoundError(f"no page images found in {path}")
    return values


def _weighted(cases: list[dict[str, Any]], renderer: str, field: str) -> float:
    weighted_sum = 0.0
    total_pages = 0
    for case in cases:
        metrics = case["visual"][renderer]
        pages = metrics["compared_page_count"]
        weighted_sum += metrics[field] * pages
        total_pages += pages
    return weighted_sum / total_pages


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    api = load_benchmark_api(manifest.compare_harness, manifest.font_aliases)
    output = args.office_output
    timings = {
        item["case_id"]: item
        for item in json.loads((output / "render-summary.json").read_text(encoding="utf-8"))
    }
    reports: list[dict[str, Any]] = []
    for case in manifest.cases:
        render_root = output / "renders" / case.case_id
        office_sources = _pages(render_root / "pages", api.module.natural_key)
        office_pages: list[Path] = []
        crop_boxes: list[tuple[int, int, int, int]] = []
        for index, source in enumerate(office_sources, start=1):
            target = output / "normalized-officecli-pages" / case.case_id / f"page-{index:02d}.png"
            crop_boxes.append(normalize_officecli_page(source, target))
            office_pages.append(target)
        word_pages = _pages(
            args.word_evidence_root / case.case_id / "word-pages", api.module.natural_key
        )
        lo_pages = _pages(
            args.lo_evidence_root / case.case_id / "optimized-lo" / "pages",
            api.module.natural_key,
        )
        office_metrics = api.module.visual_metrics(word_pages, office_pages)
        lo_metrics = api.module.visual_metrics(word_pages, lo_pages)
        triptych = output / "visual-comparisons" / f"{case.case_id}-page-01-word-officecli-lo.png"
        overview = output / "visual-comparisons" / f"{case.case_id}-document-overview.png"
        create_triptych(word_pages[0], office_pages[0], lo_pages[0], triptych)
        create_document_overview(word_pages, office_pages, lo_pages, overview)
        timing = timings[case.case_id]
        reports.append(
            {
                "case_id": case.case_id,
                "page_counts": {
                    "word": len(word_pages),
                    "officecli": len(office_pages),
                    "libreoffice_fonts": len(lo_pages),
                },
                "page_count_delta": {
                    "officecli_vs_word": len(office_pages) - len(word_pages),
                    "libreoffice_vs_word": len(lo_pages) - len(word_pages),
                },
                "page_count_ratio": {
                    "officecli_vs_word": len(office_pages) / len(word_pages),
                    "libreoffice_vs_word": len(lo_pages) / len(word_pages),
                },
                "render_seconds": timing["elapsed_seconds"],
                "officecli_pages_per_second": len(office_pages) / timing["elapsed_seconds"],
                "officecli_canvas_size": list(image_size(office_sources[0])),
                "officecli_first_page_crop_bbox": list(crop_boxes[0]),
                "officecli_normalized_size": list(image_size(office_pages[0])),
                "visual": {
                    "officecli_vs_word": office_metrics,
                    "libreoffice_vs_word": lo_metrics,
                },
                "first_page_ink_layout_similarity": {
                    "officecli_vs_word": office_metrics["per_page"][0][
                        "ink_weighted_layout_similarity"
                    ],
                    "libreoffice_vs_word": lo_metrics["per_page"][0][
                        "ink_weighted_layout_similarity"
                    ],
                },
                "first_page_horizontal_lines": {
                    "word": horizontal_line_geometry(word_pages[0]),
                    "officecli": horizontal_line_geometry(office_pages[0]),
                    "libreoffice_fonts": horizontal_line_geometry(lo_pages[0]),
                },
                "artifacts": {
                    "officecli_render_ref": str(render_root / "render-ref.json"),
                    "officecli_contact_sheet": str(render_root / "contact-sheet.png"),
                    "page_1_triptych": str(triptych),
                    "document_overview": str(overview),
                },
            }
        )
    total_word = sum(case["page_counts"]["word"] for case in reports)
    total_office = sum(case["page_counts"]["officecli"] for case in reports)
    total_lo = sum(case["page_counts"]["libreoffice_fonts"] for case in reports)
    return {
        "schema_version": 1,
        "method": {
            "officecli_version": "1.0.143",
            "platform": "macOS arm64",
            "officecli_render_path": "HTML screenshot (not Microsoft Word)",
            "officecli_canvas": "1600x1200; page cropped only for fair metric calculation",
            "comparison_dpi": 144,
            "page_pairing": "same ordinal page; divergence lowers later-page scores",
        },
        "aggregate": {
            "word_pages": total_word,
            "officecli_pages": total_office,
            "libreoffice_fonts_pages": total_lo,
            "officecli_page_count_ratio_to_word": total_office / total_word,
            "libreoffice_page_count_ratio_to_word": total_lo / total_word,
            "officecli_weighted_ink_layout_similarity": _weighted(
                reports, "officecli_vs_word", "mean_ink_weighted_layout_similarity"
            ),
            "libreoffice_weighted_ink_layout_similarity": _weighted(
                reports, "libreoffice_vs_word", "mean_ink_weighted_layout_similarity"
            ),
            "officecli_weighted_changed_pixel_ratio": _weighted(
                reports, "officecli_vs_word", "mean_changed_pixel_ratio_over_16"
            ),
            "libreoffice_weighted_changed_pixel_ratio": _weighted(
                reports, "libreoffice_vs_word", "mean_changed_pixel_ratio_over_16"
            ),
            "officecli_total_render_seconds": sum(case["render_seconds"] for case in reports),
        },
        "cases": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--office-output", type=Path, required=True)
    parser.add_argument("--word-evidence-root", type=Path, required=True)
    parser.add_argument("--lo-evidence-root", type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    target = args.office_output / "benchmark-report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
