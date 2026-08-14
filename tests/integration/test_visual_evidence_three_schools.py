from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.service import DocFitToolService

SCHOOL_TEMPLATES = (
    "01-hunau-undergraduate",
    "02-njau-undergraduate",
    "03-pku-graduate",
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="Three-school visual integration requires the locked OfficeCLI executable",
)


@pytest.mark.parametrize("case_name", SCHOOL_TEMPLATES)
def test_real_school_template_contact_page_and_object_region(
    case_name: str,
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    source = (
        repository
        / "evals"
        / "template-extraction"
        / "cases"
        / case_name
        / "gold"
        / "template.docx"
    )
    task_root = tmp_path / case_name
    task_root.mkdir()
    document = task_root / "template.docx"
    shutil.copyfile(source, document)
    service = DocFitToolService(task_root=task_root, office=OfficeCliAdapter())

    inspection = service.inspect(
        {"task_root": str(task_root), "input_docx": document.name}
    )
    target = next(
        item
        for item in inspection["objects"]
        if isinstance(item.get("text"), str)
        and len(item["text"].strip()) >= 2
        and isinstance(item.get("object_ref"), dict)
    )

    rendered, contact_images = service.render(
        {"input_docx": document.name, "overview": True}
    )
    assert rendered["renderer"]["name"] == "libreoffice"
    assert rendered["fidelity"] == "approximate"
    assert rendered["overview"]["evidence_ref"].startswith("visual:v2:")
    assert len(contact_images) == 1

    page_review, page_images = service.visual_review(
        {
            "render_ref": rendered["render_ref"],
            "mode": "pages",
            "quality": "review",
            "pages": [1],
        }
    )
    assert page_review["evidence"][0]["page"] == 1
    assert len(page_images) == 1

    region_review, region_images = service.visual_review(
        {
            "render_ref": rendered["render_ref"],
            "mode": "regions",
            "quality": "detail",
            "regions": [
                {
                    "selector": "object_ref",
                    "object_ref": target["object_ref"],
                }
            ],
        }
    )
    assert region_review["evidence"]
    assert all(
        item["evidence_ref"].startswith("visual:v2:")
        for item in region_review["evidence"]
    )
    assert region_images
