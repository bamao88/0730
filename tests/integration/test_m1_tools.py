from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from docfit.evals.synthetic_image import make_fixture_png
from docfit.template.artifact import publish_template_artifact
from docfit.tools import docx_inspect, docx_visual_review
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import ToolFailure, sha256_file
from docfit.tools.service import DocFitToolService


def _officecli(*arguments: str) -> None:
    executable = shutil.which("officecli")
    if executable is None:
        pytest.skip("M1 OfficeCLI integration requires the locked local executable")
    environment = dict(os.environ)
    environment["OFFICECLI_SKIP_UPDATE"] = "1"
    environment["OFFICECLI_RESIDENT_FLUSH"] = "each"
    completed = subprocess.run(
        [executable, *arguments, "--json"],
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["success"] is True


def _make_student(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "paragraph",
        "--prop",
        "text=原始标题",
        "--prop",
        "style=Title",
    )
    marker = path.with_name("student-marker.png")
    Image.new("RGB", (48, 48), "red").save(marker, format="PNG")
    _officecli(
        "add",
        str(path),
        "/body/p[1]",
        "--type",
        "picture",
        "--prop",
        f"src={marker}",
        "--prop",
        "width=2cm",
    )
    _officecli("add", str(path), "/body", "--type", "paragraph")
    _officecli(
        "add",
        str(path),
        "/body/p[2]",
        "--type",
        "run",
        "--prop",
        "text=在此",
    )
    _officecli(
        "add",
        str(path),
        "/body/p[2]",
        "--type",
        "run",
        "--prop",
        "text=填写正文",
    )
    _officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "table",
        "--prop",
        "rows=2",
        "--prop",
        "cols=2",
    )


def _make_template(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "paragraph",
        "--prop",
        "text=学校封面",
        "--prop",
        "style=Title",
    )
    marker = path.with_name("template-marker.png")
    marker.write_bytes(make_fixture_png())
    _officecli(
        "add",
        str(path),
        "/body/p[1]",
        "--type",
        "picture",
        "--prop",
        f"src={marker}",
        "--prop",
        "width=2cm",
    )
    _officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "paragraph",
        "--prop",
        "text=模板说明",
    )


def _ref(result: dict[str, Any], text: str) -> dict[str, Any]:
    return next(item["object_ref"] for item in result["objects"] if item["text"] == text)


def test_real_officecli_inspect_edit_import_render_review_validate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    student = tmp_path / "student.docx"
    template = tmp_path / "template.docx"
    edited = tmp_path / "edited.docx"
    _make_student(student)
    _make_template(template)
    source_hash = sha256_file(student)
    template_hash = sha256_file(template)
    student.chmod(0o444)
    template.chmod(0o444)
    service = DocFitToolService(task_root=tmp_path, office=OfficeCliAdapter())

    student_result = service.inspect({"task_root": str(tmp_path), "input_docx": student.name})
    template_result = service.inspect({"task_root": str(tmp_path), "input_docx": template.name})
    assert student_result["status"] == "ok"
    assert student_result["document"]["sha256"] == source_hash
    assert student_result["document"]["tables"] == 1
    assert all(
        set(item["object_ref"])
        == {
            "document_sha256",
            "object_id",
            "expected_fingerprint",
        }
        for item in student_result["objects"]
    )
    agent_visible_inspection = asyncio.run(
        docx_inspect.handler(
            {"task_root": str(tmp_path), "input_docx": student.name}
        )
    )
    assert json.loads(agent_visible_inspection["content"][0]["text"]) == agent_visible_inspection[
        "structuredContent"
    ]
    assert json.loads(agent_visible_inspection["content"][0]["text"])["objects"]

    edit_result = service.edit(
        {
            "task_root": str(tmp_path),
            "input_docx": template.name,
            "output_docx": edited.name,
            "operations": [
                {
                    "action": "set_properties",
                    "target_ref": _ref(template_result, "学校封面"),
                    "properties": {
                        "alignment": "center",
                        "spaceAfter": "12pt",
                        "keepWithNext": True,
                    },
                },
                {
                    "action": "replace_text",
                    "target_ref": _ref(template_result, "模板说明"),
                    "expected_text": "模板说明",
                    "replacement": "",
                },
                {
                    "action": "import_content_objects",
                    "source_docx": student.name,
                    "source_sha256": student_result["document"]["sha256"],
                    "source_refs": [
                        _ref(student_result, "原始标题"),
                        _ref(student_result, "在此填写正文"),
                        next(
                            item["object_ref"]
                            for item in student_result["objects"]
                            if item["type"] == "table"
                        ),
                    ],
                    "target_anchor_ref": _ref(template_result, "模板说明"),
                    "position": "before",
                    "include_source_final_section_properties": True,
                },
            ],
        }
    )
    assert edit_result["status"] == "ok"
    assert edit_result["committed"] is True
    assert student.stat().st_mode & 0o777 == 0o444
    assert sha256_file(student) == source_hash
    assert sha256_file(template) == template_hash
    assert edit_result["content_imports"][0]["dependency_closure_complete"] is True
    assert edit_result["content_imports"][0]["package_parts_copied"] >= 1
    assert edit_result["content_imports"][0]["relationships_copied"] >= 1
    edited_result = service.inspect({"task_root": str(tmp_path), "input_docx": edited.name})
    edited_text = [item["text"] for item in edited_result["objects"]]
    assert "学校封面" in edited_text
    assert "原始标题" in edited_text
    assert "在此填写正文" in edited_text
    assert "模板说明" not in edited_text
    edited_cover = next(item for item in edited_result["objects"] if item["text"] == "学校封面")
    assert edited_cover["format"]["alignment"] == "center"
    assert edited_cover["format"]["spaceAfter"] == "12pt"
    assert edited_cover["format"]["keepWithNext"] is True
    assert set(edited_result["document"]) >= {
        "headers",
        "footers",
        "numbering_part",
        "styles_part",
        "bookmarks",
        "fields",
        "content_controls",
        "hyperlinks",
        "merged_cells",
        "tracked_insertions",
        "tracked_deletions",
    }

    render_result, overview_images = service.render(
        {"input_docx": edited.name, "overview": True}
    )
    assert render_result["status"] == "ok"
    reference = render_result["render_ref"]
    assert reference.startswith("render:v2:")
    assert render_result["fidelity"] == "approximate"
    assert render_result["renderer"]["name"] == "libreoffice"
    assert render_result["page_count"] >= 1
    assert len(overview_images) == 1

    review, images = DocFitToolService(
        task_root=tmp_path,
        office=_BombOffice(),
        visual=service.visual(),
    ).visual_review(
        {
            "render_ref": reference,
            "mode": "pages",
            "pages": list(range(1, render_result["page_count"] + 1)),
        }
    )
    assert review["status"] == "ok"
    assert len(images) == render_result["page_count"]
    region, region_images = service.visual_review(
        {
            "render_ref": reference,
            "mode": "regions",
            "quality": "detail",
            "regions": [
                {
                    "selector": "object_ref",
                    "object_ref": next(
                        item["object_ref"]
                        for item in edited_result["objects"]
                        if item["type"] == "table"
                    ),
                }
            ],
        }
    )
    assert region["status"] == "ok"
    assert region_images
    monkeypatch.setenv("DOCFIT_TASK_ROOT", str(tmp_path))
    mcp_result = asyncio.run(
        docx_visual_review.handler(
            {
                "render_ref": reference,
                "mode": "pages",
                "pages": [1],
            }
        )
    )
    assert any(item["type"] == "image" for item in mcp_result["content"])
    assert mcp_result["structuredContent"]["status"] == "ok"

    validation = service.validate(
        {
            "task_root": str(tmp_path),
            "source_docx": student.name,
            "source_sha256": source_hash,
            "final_docx": edited.name,
        }
    )
    assert validation["status"] == "ok"
    assert validation["source_sha256"] == source_hash
    assert any(item["code"] == "verification_gap" for item in validation["warnings"])


class _BombOffice:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"visual review must not call OfficeCLI: {name}")


def test_stale_ref_and_failed_batch_publish_nothing(tmp_path: Path) -> None:
    student = tmp_path / "student.docx"
    _make_student(student)
    service = DocFitToolService(office=OfficeCliAdapter())
    inspected = service.inspect({"task_root": str(tmp_path), "input_docx": student.name})
    stale = dict(_ref(inspected, "原始标题"))
    stale["document_sha256"] = "0" * 64
    output = tmp_path / "must-not-exist.docx"
    with pytest.raises(ToolFailure, match="different document snapshot") as failure:
        service.edit(
            {
                "task_root": str(tmp_path),
                "input_docx": student.name,
                "output_docx": output.name,
                "operations": [{"action": "apply_style", "target_ref": stale, "style": "Heading1"}],
            }
        )
    assert failure.value.status == "needs_input"
    assert not output.exists()

    with pytest.raises(ToolFailure, match="absent"):
        service.edit(
            {
                "task_root": str(tmp_path),
                "input_docx": student.name,
                "output_docx": output.name,
                "operations": [
                    {
                        "action": "replace_text",
                        "target_ref": _ref(inspected, "在此填写正文"),
                        "expected_text": "不存在",
                        "replacement": "不会发布",
                    }
                ],
            }
        )
    assert not output.exists()


def test_stable_docx_edit_materializes_registry_bound_slot(tmp_path: Path) -> None:
    template = tmp_path / "template.docx"
    result = tmp_path / "result.docx"
    registry = tmp_path / "field-registry.yaml"
    _make_template(template)
    shutil.copyfile(
        Path(__file__).resolve().parents[2]
        / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml",
        registry,
    )
    source_hash = sha256_file(template)
    service = DocFitToolService(task_root=tmp_path, office=OfficeCliAdapter())
    inspected = service.inspect({"input_docx": template.name})

    edited = service.edit(
        {
            "input_docx": template.name,
            "output_docx": result.name,
            "field_registry": registry.name,
            "operations": [
                {
                    "action": "materialize_slot",
                    "target_ref": _ref(inspected, "学校封面"),
                    "field_id": "thesis.title.zh",
                }
            ],
        }
    )

    assert edited["status"] == "ok"
    assert edited["committed"] is True
    assert sha256_file(template) == source_hash
    assert edited["input_sha256"] == source_hash
    assert edited["output_sha256"] == sha256_file(result)
    final = service.inspect({"input_docx": result.name})
    control = next(item for item in final["objects"] if item["type"] == "sdt")
    assert control["format"]["alias"] == "thesis.title.zh"
    assert control["format"]["tag"].startswith("slot.thesis.title.zh.")


def test_stateless_template_publication_binds_word_contract_and_review(
    tmp_path: Path,
) -> None:
    (tmp_path / "input").mkdir()
    (tmp_path / "work").mkdir()
    (tmp_path / "output").mkdir()
    source = tmp_path / "input/school-template.docx"
    candidate = tmp_path / "work/candidate.docx"
    registry = tmp_path / "input/field-registry.yaml"
    _make_template(source)
    # The generic integration fixture deliberately references a missing Title
    # style.  Publication tests objective style evidence, so use the defined
    # Normal style for this focused artifact test.
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    parts["word/document.xml"] = parts["word/document.xml"].replace(
        b'<w:pStyle w:val="Title" />', b'<w:pStyle w:val="Normal" />'
    )
    with zipfile.ZipFile(source, "w") as archive:
        for info in infos:
            archive.writestr(info, parts[info.filename])
    shutil.copyfile(
        Path(__file__).resolve().parents[2]
        / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml",
        registry,
    )
    service = DocFitToolService(task_root=tmp_path, office=OfficeCliAdapter())
    inspected = service.inspect({"input_docx": str(source)})
    service.edit(
        {
            "input_docx": str(source),
            "output_docx": str(candidate),
            "field_registry": str(registry),
            "operations": [
                {
                    "action": "materialize_slot",
                    "target_ref": _ref(inspected, "学校封面"),
                    "field_id": "thesis.title.zh",
                }
            ],
        }
    )
    candidate_hash = sha256_file(candidate)

    receipt = publish_template_artifact(
        task_root=tmp_path,
        source_docx=source,
        candidate_docx=candidate,
        field_registry=registry,
        validation={"final_sha256": candidate_hash, "status": "ok"},
        visual_review={
            "document_sha256": candidate_hash,
            "render_ref": "render:v2:" + "0" * 64,
            "reviewed_pages": [1],
            "findings": [],
        },
        office=OfficeCliAdapter(),
    )

    output = tmp_path / "output/final-template.docx"
    contract = tmp_path / "output/fill-contract.json"
    assert receipt["published"] is True
    assert receipt["template_sha256"] == candidate_hash == sha256_file(output)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    assert payload["template_sha256"] == candidate_hash
    assert payload["slots"][0]["field_id"] == "thesis.title.zh"


def test_paths_outside_task_root_and_source_overwrite_are_denied(tmp_path: Path) -> None:
    student = tmp_path / "student.docx"
    _make_student(student)
    service = DocFitToolService(office=OfficeCliAdapter())
    inspected = service.inspect({"task_root": str(tmp_path), "input_docx": student.name})
    with pytest.raises(ToolFailure) as outside:
        service.inspect({"task_root": str(tmp_path), "input_docx": "/etc/hosts"})
    assert outside.value.code == "path_not_authorized"
    with pytest.raises(ToolFailure) as overwrite:
        service.edit(
            {
                "task_root": str(tmp_path),
                "input_docx": student.name,
                "output_docx": student.name,
                "operations": [
                    {
                        "action": "apply_style",
                        "target_ref": _ref(inspected, "原始标题"),
                        "style": "Heading1",
                    }
                ],
            }
        )
    assert overwrite.value.code == "source_overwrite_denied"
