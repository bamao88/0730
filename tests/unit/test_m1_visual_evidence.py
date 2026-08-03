from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from docfit.tools.images import create_contact_sheet, image_metadata
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file, sha256_json
from docfit.tools.service import DocFitToolService


class _BombOffice:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"visual evidence reuse must not invoke a backend: {name}")


def _render(
    root: Path,
    name: str,
    *,
    color: str,
    document: Path,
) -> Path:
    directory = root / name
    pages = directory / "pages"
    pages.mkdir(parents=True)
    page = pages / "page-0001.png"
    Image.new("RGB", (240, 320), color).save(page)
    contact = directory / "contact-sheet.png"
    contact_metadata = create_contact_sheet([page], contact)
    reference = {
        "schema_version": 1,
        "document_path": str(document),
        "document_sha256": sha256_file(document),
        "render_sha256": sha256_json({"name": name, "page": sha256_file(page)}),
        "render_intent": "edit_feedback",
        "fidelity": "approximate",
        "provider": {"name": "officecli", "version": "1.0.143"},
        "font_environment": {"fingerprint": "synthetic", "substitutions": []},
        "page_count": 1,
        "dpi": 144,
        "artifacts": {
            "pages": [{"page": 1, "path": str(page), **image_metadata(page)}],
            "contact_sheet": {"path": str(contact), **contact_metadata},
        },
    }
    path = directory / "render-ref.json"
    atomic_write_json(path, reference)
    return path


def test_existing_render_supports_contact_crop_and_compare_without_backend(tmp_path: Path) -> None:
    document = tmp_path / "document.docx"
    document.write_bytes(b"synthetic-snapshot")
    baseline = _render(tmp_path, "baseline", color="white", document=document)
    current = _render(tmp_path, "current", color="lightblue", document=document)
    service = DocFitToolService(office=_BombOffice())  # type: ignore[arg-type]
    initial_refs = set(tmp_path.rglob("render-ref.json"))

    contact, contact_images = service.visual_review(
        {
            "task_root": str(tmp_path),
            "render_ref": str(current),
            "mode": "contact_sheet",
        }
    )
    crops, crop_images = service.visual_review(
        {
            "task_root": str(tmp_path),
            "render_ref": str(current),
            "mode": "crops",
            "crops": [{"page": 1, "bbox": [10, 10, 100, 100]}],
        }
    )
    comparison, comparison_images = service.visual_review(
        {
            "task_root": str(tmp_path),
            "render_ref": str(current),
            "baseline_render_ref": str(baseline),
            "mode": "compare",
            "pages": [1],
        }
    )

    assert contact["mode"] == "contact_sheet"
    assert crops["evidence"][0]["view"] == "crop"
    assert comparison["evidence"][0]["view"] == "baseline_current_difference"
    assert all(path.is_file() for path in contact_images + crop_images + comparison_images)
    assert set(tmp_path.rglob("render-ref.json")) == initial_refs


def test_existing_render_is_rejected_after_document_changes(tmp_path: Path) -> None:
    document = tmp_path / "document.docx"
    document.write_bytes(b"snapshot-one")
    current = _render(tmp_path, "current", color="white", document=document)
    document.write_bytes(b"snapshot-two")

    with pytest.raises(ToolFailure) as failure:
        DocFitToolService(office=_BombOffice()).visual_review(  # type: ignore[arg-type]
            {
                "task_root": str(tmp_path),
                "render_ref": str(current),
                "mode": "pages",
                "pages": [1],
            }
        )

    assert failure.value.code == "render_document_changed"
