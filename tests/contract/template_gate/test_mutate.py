from __future__ import annotations

import asyncio
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from docfit.template.comparison import TemplateComparisonService
from docfit.template.compile_mutation import compile_mutation_decisions
from docfit.template.observation import TemplateObservationService
from docfit.tools.runtime import sha256_file
from docfit.tools.template_tools import template_compare, template_mutate

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    PROJECT_ROOT
    / "evals/template-extraction/fixtures/S08-forbidden-residue/actual-template.docx"
)
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _add_label_before_placeholder(source: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    paragraph = list(root.iter(f"{W}p"))[1]
    original_run = paragraph.find(f"{W}r")
    assert original_run is not None
    original_text = original_run.find(f"{W}t")
    assert original_text is not None
    original_text.text = "姓名："
    placeholder_run = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(placeholder_run, f"{W}t").text = "请在此填写"
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(source, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])


def test_materialize_then_remove_commits_one_safe_docx_and_evidence(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    (task_root / "input").mkdir(parents=True)
    (task_root / "work/decisions").mkdir(parents=True)
    (task_root / "work/compiled").mkdir()
    (task_root / "work/attempts").mkdir()
    (task_root / "output").mkdir()
    source = task_root / "input/template.docx"
    registry = task_root / "input/content-fields.yaml"
    shutil.copyfile(FIXTURE, source)
    _add_label_before_placeholder(source)
    shutil.copyfile(REGISTRY, registry)
    source_hash = sha256_file(source)
    observed = TemplateObservationService().create(
        {
            "input_docx": "input/template.docx",
            "visual_level": "none",
            "focus": ["structure", "slot_candidates"],
        },
        task_root=task_root,
    )
    target = next(
        item
        for item in observed["objects"]
        if item["kind"] == "run" and item["text"] == "请在此填写"
    )
    execution_locator = {
        "snapshot_ref": observed["snapshot_ref"],
        "object_id": target["object_id"],
        "expected_fingerprint": target["expected_fingerprint"],
    }
    decisions = {
        "schema_version": 1,
        "snapshot_ref": observed["snapshot_ref"],
        "document_sha256": source_hash,
        "field_registry_ref": {
            "path": "input/content-fields.yaml",
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.1.0",
            "sha256": sha256_file(registry),
        },
        "sources": [
            {
                "source_id": "school-template",
                "path": "input/template.docx",
                "sha256": source_hash,
                "authority": "supplied_school_template",
                "scope": "template_structure",
            }
        ],
        "decisions": [
            {
                "decision_id": "decision-title-slot",
                "subject": "封面中文题名",
                "responsibility": {
                    "kind": "fill",
                    "content_type": "text",
                    "cardinality": "one",
                    "required": True,
                    "condition": None,
                    "handling": "automatic",
                },
                "source_refs": ["school-template"],
                "evidence_refs": [observed["snapshot_ref"]],
                "rationale": "模板明确提供该填写位置",
            },
            {
                "decision_id": "decision-remove-example",
                "subject": "清理示例文字",
                "responsibility": {
                    "kind": "fill",
                    "content_type": "text",
                    "cardinality": "one",
                    "required": True,
                    "condition": None,
                    "handling": "automatic",
                },
                "source_refs": ["school-template"],
                "evidence_refs": [observed["snapshot_ref"]],
                "rationale": "填写责任迁移到已物化槽位",
            },
        ],
        "operations": [
            {
                "operation_id": "op-title-slot",
                "operation": "materialize_slot",
                "decision_ref": "decision-title-slot",
                "execution_locator": execution_locator,
                "slot_id": "slot.cover.thesis_title",
                "field_id": "thesis.title.zh",
                "content_type": "text",
                "required": True,
                "cardinality": "one",
                "marker": {
                    "protocol": "docfit-content-control-marker/v1",
                    "alias": "thesis.title.zh",
                    "tag": "slot.cover.thesis_title",
                },
                "preserve_container": True,
                "expected_after": {
                    "content_control_count": 1,
                    "visible_placeholder_text": False,
                },
            },
            {
                "operation_id": "op-remove-example",
                "operation": "remove_content",
                "decision_ref": "decision-remove-example",
                "execution_locator": execution_locator,
                "mode": "clear_text_preserve_container",
                "migration_targets": [
                    {
                        "responsibility_ref": "decision-title-slot",
                        "target_kind": "materialized_slot",
                        "slot_id": "slot.cover.thesis_title",
                    }
                ],
                "deletion_authority": None,
                "expected_after": {
                    "forbidden_text_absent": "请在此填写",
                    "container_preserved": True,
                },
            },
        ],
    }
    decision_path = task_root / "work/decisions/mutation-decisions.yaml"
    decision_path.write_text(yaml.safe_dump(decisions, allow_unicode=True), encoding="utf-8")
    plan_path = task_root / "work/compiled/mutation-plan.json"
    compile_mutation_decisions(
        task_root=task_root,
        input_path=decision_path,
        output_path=plan_path,
    )

    result = asyncio.run(
        template_mutate.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "mutation_plan_path": "work/compiled/mutation-plan.json",
                "output_docx": "work/attempts/template-attempt-1.docx",
            }
        )
    )["structuredContent"]

    assert result["call_status"] == "ok"
    assert result["result_state"] == "mutated"
    assert result["committed"] is True
    assert result["after_snapshot_ref"].startswith("snapshot:v1:")
    assert result["mutation_ref"].startswith("mutation:v1:")
    assert sha256_file(source) == source_hash
    output = task_root / result["output_docx"]
    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = list(root.iter(f"{W}p"))
    controls = list(root.iter(f"{W}sdt"))
    managed = next(
        control
        for control in controls
        if control.find(f"{W}sdtPr/{W}tag").get(f"{W}val") == "slot.cover.thesis_title"
    )
    assert len(paragraphs) == 2
    assert managed.find(f"{W}sdtPr/{W}alias").get(f"{W}val") == "thesis.title.zh"
    assert "".join(item.text or "" for item in managed.iter(f"{W}t")) == ""
    assert "请在此填写" not in "".join(item.text or "" for item in root.iter(f"{W}t"))
    assert "姓名：" in "".join(item.text or "" for item in paragraphs[1].iter(f"{W}t"))
    assert "姓名：" not in "".join(item.text or "" for item in managed.iter(f"{W}t"))

    comparison_request = {
        "schema_version": 1,
        "task_root": str(task_root),
        "action": "create",
        "review_mode": "mutation_review",
        "before_snapshot_ref": observed["snapshot_ref"],
        "after_snapshot_ref": result["after_snapshot_ref"],
        "mutation_ref": result["mutation_ref"],
    }
    TemplateComparisonService().review(comparison_request, task_root=task_root)
    compared = asyncio.run(template_compare.handler(comparison_request))["structuredContent"]
    assert compared["call_status"] == "ok", compared
    assert compared["unexpected_changes"] == []
    assert compared["machine_blockers"] == []
    assert {item["kind"] for item in compared["expected_changes"]} == {
        "content_control_added",
        "target_text_changed",
    }


def test_agent_authorized_paragraph_cleanup_is_not_semantically_vetoed(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    (task_root / "input").mkdir(parents=True)
    (task_root / "work/decisions").mkdir(parents=True)
    (task_root / "work/compiled").mkdir()
    (task_root / "work/attempts").mkdir()
    (task_root / "output").mkdir()
    source = task_root / "input/template.docx"
    registry = task_root / "input/content-fields.yaml"
    shutil.copyfile(FIXTURE, source)
    _add_label_before_placeholder(source)
    shutil.copyfile(REGISTRY, registry)
    source_hash = sha256_file(source)
    observed = TemplateObservationService().create(
        {
            "input_docx": "input/template.docx",
            "visual_level": "none",
            "focus": ["structure"],
        },
        task_root=task_root,
    )
    target = next(
        item
        for item in observed["objects"]
        if item["kind"] == "paragraph" and item["text"] == "姓名：请在此填写"
    )
    decisions = {
        "schema_version": 1,
        "snapshot_ref": observed["snapshot_ref"],
        "document_sha256": source_hash,
        "field_registry_ref": {
            "path": "input/content-fields.yaml",
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.1.0",
            "sha256": sha256_file(registry),
        },
        "sources": [
            {
                "source_id": "school-template",
                "path": "input/template.docx",
                "sha256": source_hash,
                "authority": "supplied_school_template",
                "scope": "template_structure",
            }
        ],
        "decisions": [
            {
                "decision_id": "decision-clear-paragraph",
                "subject": "清理 Agent 已确认的整段模板说明",
                "responsibility": {
                    "kind": "remove",
                    "content_type": "text",
                    "cardinality": "one",
                    "required": False,
                    "condition": None,
                    "handling": "automatic",
                },
                "source_refs": ["school-template"],
                "evidence_refs": [observed["snapshot_ref"]],
                "rationale": "Agent 已根据任务上下文明确授权清理整个段落",
            }
        ],
        "operations": [
            {
                "operation_id": "op-clear-paragraph",
                "operation": "remove_content",
                "decision_ref": "decision-clear-paragraph",
                "execution_locator": {
                    "snapshot_ref": observed["snapshot_ref"],
                    "object_id": target["object_id"],
                    "expected_fingerprint": target["expected_fingerprint"],
                },
                "mode": "clear_text_preserve_container",
                "migration_targets": [],
                "deletion_authority": {
                    "source_ref": "school-template",
                    "authority_sha256": source_hash,
                },
                "expected_after": {
                    "forbidden_text_absent": "姓名：请在此填写",
                    "container_preserved": True,
                },
            }
        ],
    }
    decision_path = task_root / "work/decisions/mutation-decisions.yaml"
    decision_path.write_text(yaml.safe_dump(decisions, allow_unicode=True), encoding="utf-8")
    plan_path = task_root / "work/compiled/mutation-plan.json"
    compile_mutation_decisions(
        task_root=task_root,
        input_path=decision_path,
        output_path=plan_path,
    )

    result = asyncio.run(
        template_mutate.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "mutation_plan_path": "work/compiled/mutation-plan.json",
                "output_docx": "work/attempts/template-attempt-1.docx",
            }
        )
    )["structuredContent"]

    assert result["call_status"] == "ok", result
    assert result["committed"] is True
    assert {item["name"] for item in result["checks"]} == {
        "source_unchanged",
        "compiled_plan_executed",
        "docx_package_valid",
        "output_published_atomically",
    }
    assert result["warnings"] == [
        {
            "code": "agent_semantic_review_required",
            "message": (
                "The tool does not judge semantic correctness. Review the mutation "
                "diff and rendered pages before building the artifact."
            ),
        }
    ]
    assert sha256_file(source) == source_hash
    output = task_root / result["output_docx"]
    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    cleared = list(root.iter(f"{W}p"))[1]
    assert "".join(item.text or "" for item in cleared.iter(f"{W}t")) == ""


def test_mutate_rejects_inline_operations(tmp_path: Path) -> None:
    result = asyncio.run(
        template_mutate.handler(
            {
                "schema_version": 1,
                "task_root": str(tmp_path),
                "mutation_plan_path": "work/compiled/plan.json",
                "output_docx": "work/attempts/output.docx",
                "operations": [],
            }
        )
    )["structuredContent"]

    assert result["call_status"] == "needs_input"
