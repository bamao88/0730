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
import yaml
from PIL import Image

from docfit.evals.synthetic_image import make_fixture_png
from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import publish_template_artifact
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools import docx_inspect, docx_visual_review
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from docfit.tools.service import DocFitToolService
from docfit.visual.renderer import DEFAULT_IMAGE
from tests.support.source_identity import persist_source_identity, review_binding, source_partition


def _visual_renderer_ready() -> bool:
    executable = shutil.which("docker")
    if executable is None:
        return False
    completed = subprocess.run(
        [executable, "inspect", "--type=image", DEFAULT_IMAGE],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return completed.returncode == 0


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


SOURCE_ENTRY_ID = "source-entry-school-cover"


def _span_ref(source_sha256: str) -> str:
    return (
        f"source_entry_id={SOURCE_ENTRY_ID};extent=text[0:4];source_snapshot_sha256={source_sha256}"
    )


def _slot_ref(field_id: str, source_sha256: str) -> str:
    return f"{_span_ref(source_sha256)};field_id={field_id}"


def _write_template_slot_provenance(
    root: Path,
    *,
    field_id: str,
    source_sha256: str,
    registry: Path,
    candidate: Path,
    inspected: dict[str, Any],
) -> None:
    span_ref = _span_ref(source_sha256)
    slot_ref = _slot_ref(field_id, source_sha256)
    harness_dir = root / "work/.docfit/harness"
    materialization_dir = root / "work/.docfit/post-unit-materialization"
    harness_dir.mkdir(parents=True, exist_ok=True)
    materialization_dir.mkdir(parents=True, exist_ok=True)
    source_object = next(item for item in inspected["objects"] if item.get("text") == "学校封面")
    object_ref = source_object["object_ref"]
    vocabulary = FieldRegistrySnapshot.load(registry).pre_input_vocabulary()
    inventory = {
        "schema_version": 2,
        "document_sha256": source_sha256,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "source_entries": [
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "text": "学校封面",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": object_ref["object_id"],
                        "locator": source_object["locator"],
                        "fingerprint": object_ref["expected_fingerprint"],
                        "object_ref": object_ref,
                        "text_span": [0, 4],
                    }
                ],
            }
        ],
        "objects": [{**source_object, "source_entry_id": SOURCE_ENTRY_ID}],
        "reading_blocks": [],
    }
    agent_judgments = [
        {
            "source_entry_id": SOURCE_ENTRY_ID,
            "parts": [
                {
                    "text": "学校封面",
                    "role": "fill_slot",
                    "field_id": field_id,
                }
            ],
        }
    ]
    source_partition(inventory)
    persist_source_identity(root, inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=agent_judgments,
    )
    semantic_judgments = [{**agent_judgments[0], "resolved_spans": resolved}]
    semantic_digest = sha256_json(semantic_judgments)
    (harness_dir / "object-inventory.json").write_text(
        json.dumps(inventory),
        encoding="utf-8",
    )
    (harness_dir / "semantic-judgments.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "document_sha256": source_sha256,
                **review_binding(inventory),
                "field_id_vocabulary": vocabulary,
                "field_vocabulary_digest": vocabulary["digest"],
                "semantic_judgments_sha256": semantic_digest,
                "judgment_count": 1,
                "semantic_judgments": semantic_judgments,
                "resolved_spans": resolved,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (materialization_dir / "materialization.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "ok",
                "document_sha256": source_sha256,
                **review_binding(inventory),
                "semantic_judgments_sha256": semantic_digest,
                "field_vocabulary_digest": vocabulary["digest"],
                "field_registry_ref": FieldRegistrySnapshot.load(registry).identity(),
                # Synthetic provenance; this tests publication, not materialization.
                "effect_verification": {
                    "schema_version": 3, "status": "ok", "reopened_package": True,
                    "source_sha256": source_sha256,
                    "semantic_judgments_sha256": semantic_digest,
                    "candidate_sha256": sha256_file(candidate),
                },
                "operations": [
                    {
                        "action": "materialize_slot",
                        "field_id": field_id,
                        "span_ref": span_ref,
                        "slot_ref": slot_ref,
                        "source_entry_id": SOURCE_ENTRY_ID,
                        "word_fragments": resolved[0]["word_fragments"],
                    }
                ],
                "mutation_receipts": [
                    {
                        "receipt_type": "mutation",
                        "field_ids": [field_id],
                        "span_refs": [span_ref],
                        "slot_refs": [slot_ref],
                        "operation": {
                            "action": "materialize_slot",
                            "field_id": field_id,
                            "span_ref": span_ref,
                            "slot_ref": slot_ref,
                            "source_entry_id": SOURCE_ENTRY_ID,
                            "word_fragments": resolved[0]["word_fragments"],
                        },
                    }
                ],
                "write": {"status": "ok", "output_sha256": sha256_file(candidate)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.skipif(
    not _visual_renderer_ready(),
    reason="M1 render/review integration requires the fixed Docker LibreOffice renderer",
)
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
        docx_inspect.handler({"task_root": str(tmp_path), "input_docx": student.name})
    )
    assert (
        json.loads(agent_visible_inspection["content"][0]["text"])
        == agent_visible_inspection["structuredContent"]
    )
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

    render_result, overview_images = service.render({"input_docx": edited.name, "overview": True})
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


def test_docx_inspect_output_mode_returns_bounded_object_window(tmp_path: Path) -> None:
    template = tmp_path / "template.docx"
    _make_template(template)
    (tmp_path / "work/.docfit").mkdir(parents=True)
    service = DocFitToolService(task_root=tmp_path, office=OfficeCliAdapter())

    result = service.inspect(
        {
            "input_docx": template.name,
            "focus": ["structure"],
            "output": "work/.docfit/source-inventory.json",
            "object_limit": 2,
        }
    )

    full = json.loads((tmp_path / "work/.docfit/source-inventory.json").read_text(encoding="utf-8"))
    assert result["analysis_path"].endswith("work/.docfit/source-inventory.json")
    assert result["object_count"] == len(full["objects"])
    assert result["object_window"]["returned"] == 2
    assert len(result["objects"]) == 2
    assert "locator" in result["objects"][0]
    assert len(full["objects"]) >= len(result["objects"])


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
                    "slot_ref": _slot_ref("thesis.title.zh", source_hash),
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
    assert control["format"]["tag"] == _slot_ref("thesis.title.zh", source_hash)


def test_stateless_template_publication_binds_word_contract_and_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    source_hash = sha256_file(source)
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
                    "slot_ref": _slot_ref("thesis.title.zh", source_hash),
                }
            ],
        }
    )
    candidate_hash = sha256_file(candidate)
    _write_template_slot_provenance(
        tmp_path,
        field_id="thesis.title.zh",
        source_sha256=source_hash,
        registry=registry,
        candidate=candidate,
        inspected=inspected,
    )

    # Real Word/contract publication is exercised below. Page-review acceptance
    # is explicitly isolated, not fabricated as a human or visual-model verdict.
    # test_final_visual_review.py exercises missing, stale and blocked reviews.
    review_checks: list[tuple[str, str]] = []

    def isolated_review(_review, *, candidate_hash, source_hash, store):
        review_checks.append((candidate_hash, source_hash))

    monkeypatch.setattr(
        "docfit.template.artifact.validate_final_visual_review", isolated_review
    )
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
    contract = tmp_path / "output/fill-contract.yaml"
    assert receipt["published"] is True
    assert review_checks == [(candidate_hash, source_hash)]
    assert receipt["template_sha256"] == candidate_hash == sha256_file(output)
    assert receipt["fill_contract_path"] == "output/fill-contract.yaml"
    assert not (tmp_path / "output/fill-contract.json").exists()
    payload = yaml.safe_load(contract.read_text(encoding="utf-8"))
    assert payload["template_sha256"] == candidate_hash
    assert payload["slots"][0]["field_id"] == "thesis.title.zh"
    assert payload["slots"][0]["slot_ref"] == _slot_ref(
        "thesis.title.zh",
        source_hash,
    )


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
