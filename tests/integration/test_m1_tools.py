from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from docfit.tools import docx_inspect, docx_visual_review
from docfit.tools.image_smoke import make_smoke_png
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
    marker.write_bytes(make_smoke_png())
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


def test_real_officecli_inspect_edit_import_render_review_validate(tmp_path: Path) -> None:
    student = tmp_path / "student.docx"
    template = tmp_path / "template.docx"
    edited = tmp_path / "edited.docx"
    _make_student(student)
    _make_template(template)
    source_hash = sha256_file(student)
    template_hash = sha256_file(template)
    student.chmod(0o444)
    template.chmod(0o444)
    service = DocFitToolService(office=OfficeCliAdapter())

    student_result = service.inspect({"task_root": str(tmp_path), "input_docx": student.name})
    template_result = service.inspect({"task_root": str(tmp_path), "input_docx": template.name})
    assert student_result["status"] == "ok"
    assert student_result["document"]["sha256"] == source_hash
    assert student_result["document"]["tables"] == 1
    assert all(
        set(item["object_ref"])
        == {
            "schema_version",
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

    render_result = service.render(
        {
            "task_root": str(tmp_path),
            "input_docx": edited.name,
            "render_intent": "edit_feedback",
            "output_dir": "render-cli",
            "focus_object_refs": [
                next(
                    item["object_ref"]
                    for item in edited_result["objects"]
                    if item["type"] == "table"
                )
            ],
        }
    )
    assert render_result["status"] == "ok"
    reference = render_result["render_ref"]
    assert reference["fidelity"] == "approximate"
    assert reference["provider"]["name"] == "officecli"
    assert reference["artifacts"]["pdf"] is None
    assert reference["page_count"] >= 1
    layout_map = json.loads(Path(reference["artifacts"]["layout_map"]).read_text(encoding="utf-8"))
    mapped = [element for page_record in layout_map["pages"] for element in page_record["elements"]]
    assert len(mapped) == 1
    assert mapped[0]["type"] == "table"
    assert mapped[0]["mapping_quality"] == "approximate"
    assert len(mapped[0]["bbox"]) == 4

    review, images = DocFitToolService(office=_BombOffice()).visual_review(
        {
            "task_root": str(tmp_path),
            "render_ref": "render-cli",
            "mode": "pages",
            "pages": list(range(1, reference["page_count"] + 1)),
        }
    )
    assert review["status"] == "ok"
    assert len(images) == reference["page_count"]
    mcp_result = asyncio.run(
        docx_visual_review.handler(
            {
                "task_root": str(tmp_path),
                "render_ref": "render-cli",
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
