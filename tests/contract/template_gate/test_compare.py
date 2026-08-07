from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from PIL import Image

from docfit.template.observation import TemplateObservationService
from docfit.tools.runtime import atomic_write_json, sha256_file
from docfit.tools.template_tools import template_compare
from docfit.visual.evidence import render_reference, visual_reference

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
)


def _seed_two_pages(task_root: Path, document_sha256: str) -> tuple[str, list[str]]:
    renderer = {
        "name": "libreoffice",
        "version": "LibreOffice 25.2.3.2 520(Build:2)",
        "container_image_digest": "sha256:test",
        "font_environment_digest": "f" * 64,
        "locale": "zh_CN.UTF-8",
        "pdf_export_options": "test",
    }
    render_ref = render_reference(
        {"document_sha256": document_sha256, "renderer": renderer}
    )
    root = task_root / ".docfit/evidence/renders" / render_ref.rsplit(":", 1)[-1]
    views = root / "views"
    views.mkdir(parents=True)
    pdf = root / "document.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% test\n")
    atomic_write_json(
        root / "manifest.json",
        {
            "schema_version": 2,
            "render_ref": render_ref,
            "document_sha256": document_sha256,
            "page_count": 2,
            "fidelity": "approximate",
            "renderer": renderer,
            "files": [{"path": "document.pdf", "sha256": sha256_file(pdf)}],
        },
    )
    refs: list[str] = []
    for page in (1, 2):
        identity = {"render_ref": render_ref, "view": "page", "page": page, "dpi": 144}
        ref = visual_reference(identity)
        image = views / f"page-{page:04d}-{ref.rsplit(':', 1)[-1]}.png"
        Image.new("RGB", (50, 70), (20, page * 40, 20)).save(image)
        atomic_write_json(
            image.with_suffix(".json"),
            {
                "schema_version": 2,
                "evidence_ref": ref,
                "render_ref": render_ref,
                "identity": identity,
                "image_sha256": sha256_file(image),
                "page": page,
                "pages": [page],
            },
        )
        refs.append(ref)
    return render_ref, refs


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
            "focus": ["structure"],
        },
        task_root=task_root,
    )
    render_ref, evidence_refs = _seed_two_pages(
        task_root, str(observed["document_sha256"])
    )

    compared = asyncio.run(
        template_compare.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "create",
                "review_mode": "final_review",
                "final_snapshot_ref": observed["snapshot_ref"],
                "render_ref": render_ref,
                "reviewed_pages": [1, 2],
                "evidence_refs": evidence_refs,
                "findings": [],
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

    assert [item["evidence_ref"] for item in compared["required_images"]] == evidence_refs


def test_compare_tool_does_not_accept_agent_dispositions(tmp_path: Path) -> None:
    result = asyncio.run(
        template_compare.handler(
            {
                "schema_version": 1,
                "task_root": str(tmp_path),
                "action": "create",
                "review_mode": "final_review",
                "final_snapshot_ref": "snapshot:v1:00000000000000000000000000000000",
                "image_dispositions": [],
            }
        )
    )["structuredContent"]

    assert result["call_status"] == "needs_input"
