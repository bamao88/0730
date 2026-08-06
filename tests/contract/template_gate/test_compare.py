from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from PIL import Image

from docfit.template.comparison import TemplateComparisonService
from docfit.template.observation import TemplateObservationService
from docfit.template.ports import RenderedDocument
from docfit.tools.template_tools import template_compare

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
)


class _TwoPageRenderer:
    def render(
        self,
        document: Path,
        *,
        visual_level: str,
        output: Path,
    ) -> RenderedDocument:
        assert visual_level == "candidate_verification"
        pages_directory = output / "pages"
        pages_directory.mkdir()
        pages = []
        for page_number in (1, 2):
            page = pages_directory / f"page-{page_number:04d}.png"
            Image.new("RGB", (50, 70), (20, page_number * 40, 20)).save(page)
            pages.append(page)
        return RenderedDocument(tuple(pages), {"name": "fake-boundary"})


def test_final_compare_requires_every_candidate_page_without_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task_root = tmp_path / "task"
    (task_root / "input").mkdir(parents=True)
    (task_root / "work").mkdir()
    (task_root / "output").mkdir()
    shutil.copyfile(FIXTURE, task_root / "input/template.docx")
    observed = TemplateObservationService().create(
        {
            "input_docx": "input/template.docx",
            "visual_level": "none",
            "focus": ["structure"],
        },
        task_root=task_root,
    )
    comparison_service = TemplateComparisonService(_TwoPageRenderer())
    monkeypatch.setattr(
        "docfit.tools.template_tools.TemplateComparisonService",
        lambda: comparison_service,
    )

    compared = asyncio.run(
        template_compare.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "create",
                "review_mode": "final_review",
                "final_snapshot_ref": observed["snapshot_ref"],
                "visual_level": "candidate_verification",
            }
        )
    )["structuredContent"]

    assert compared["call_status"] == "ok"
    assert compared["result_state"] == "compared"
    assert compared["comparison_ref"].startswith("comparison:v1:")
    assert compared["expected_changes"] == []
    assert compared["unexpected_changes"] == []
    assert compared["machine_blockers"] == []
    assert [item["pages"] for item in compared["required_images"]] == [[1], [2]]
    assert all(item["kind"] == "final_full_page" for item in compared["required_images"])

    images = asyncio.run(
        template_compare.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "images",
                "comparison_ref": compared["comparison_ref"],
                "required_image_ids": [
                    item["required_image_id"] for item in compared["required_images"]
                ],
                "max_images": 2,
            }
        )
    )
    assert len(images["structuredContent"]["images"]) == 2
    assert len([item for item in images["content"] if item["type"] == "image"]) == 2


def test_compare_tool_does_not_accept_agent_dispositions(tmp_path: Path) -> None:
    result = asyncio.run(
        template_compare.handler(
            {
                "schema_version": 1,
                "task_root": str(tmp_path),
                "action": "create",
                "review_mode": "final_review",
                "final_snapshot_ref": "snapshot:v1:00000000000000000000000000000000",
                "visual_level": "candidate_verification",
                "image_dispositions": [],
            }
        )
    )["structuredContent"]

    assert result["call_status"] == "needs_input"
