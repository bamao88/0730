from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk.types import AssistantMessage, ResultMessage, StreamEvent, ToolUseBlock

from docfit.app.cli import build_parser
from docfit.app.prepare_template import (
    UNIT_BOUNDARY_OUTPUT_SCHEMA,
    PreparedTemplateTask,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _ensure_post_unit_inventory,
    _post_unit_checkpoint_report,
    _post_unit_inventory_from_checkpoint,
    _run_backend,
    _run_unit_boundary_checkpoint,
    _sdk_receive_event,
    _select_host_candidate_for_accepted_semantics,
    _semantic_coverage_feedback,
    _unit_boundary_checkpoint_payload,
    _validate_unit_boundary_checkpoint,
    build_prepare_template_prompt,
    build_unit_boundary_checkpoint_prompt,
    prepare_template_task,
    run_prepare_template,
)
from docfit.app.settings import AgentBackend
from docfit.fields import FieldRegistrySnapshot
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json


def _prepared(tmp_path: Path) -> PreparedTemplateTask:
    template = tmp_path / "input/school-template.docx"
    registry = tmp_path / "input/field-registry.yaml"
    requirements = tmp_path / "input/school-requirements.pdf"
    template.parent.mkdir(parents=True)
    template.write_bytes(b"template")
    registry.write_text(
        "registry_id: test\n"
        "registry_version: v1\n"
        "fields:\n"
        "  - field_id: author.name.zh\n"
        "    label: Author name\n"
        "    meaning: Student author name.\n"
        "    content_type: text\n"
        "    cardinality: single\n",
        encoding="utf-8",
    )
    requirements.write_bytes(b"%PDF-1.4\n")
    return PreparedTemplateTask(
        task_root=tmp_path,
        template_path=template,
        requirements_path=requirements,
        registry_source=registry,
        template_sha256="a" * 64,
        requirements_sha256="c" * 64,
        registry_sha256="b" * 64,
    )


def _unit_checkpoint(prepared: PreparedTemplateTask) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ok",
        "checkpoint": "unit-boundary",
        "source_hash": prepared.template_sha256,
        "summary": "Accepted one synthetic top-level unit.",
        "unit_count": 1,
        "units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_boundary": {"page": 1, "seen_text": "start"},
                "end_boundary": {"page": 1, "seen_text": "end"},
            }
        ],
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_locator": "/body/p[1]",
                "end_locator": "/body/p[1]",
            }
        ],
        "backend": "test",
        "session_id": "unit-session",
        "tool_uses": ["Skill", "mcp__docfit__docfit_evidence"],
        "skills_loaded": ["docfit-school-extract"],
        "sdk_query_count": 1,
        "harness_feedback_attempts": 0,
        "wall_duration_ms": 5,
    }


def _request(tmp_path: Path, **overrides: object) -> PrepareTemplateRequest:
    template = tmp_path / "source.docx"
    registry = tmp_path / "registry.yaml"
    template.write_bytes(b"template")
    registry.write_text(
        "registry_id: test\n"
        "registry_version: v1\n"
        "fields:\n"
        "  - field_id: author.name.zh\n"
        "    label: Author name\n"
        "    meaning: Student author name.\n"
        "    content_type: text\n"
        "    cardinality: single\n",
        encoding="utf-8",
    )
    values = {
        "school_template": template,
        "output_directory": tmp_path / "task",
        "field_registry": registry,
    }
    values.update(overrides)
    return PrepareTemplateRequest(**values)  # type: ignore[arg-type]


def _backend() -> AgentBackend:
    return AgentBackend(
        name="test",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def _source_noop_agent_semantic_judgments() -> list[dict[str, object]]:
    block_id = "u-all:block-0001"
    return [
        {
            "scope": {"reading_block_id": block_id},
            "parts": [{"text": "source already complete", "role": "manual_region"}],
        }
    ]


def _source_noop_semantic_judgments() -> list[dict[str, object]]:
    block_id = "u-all:block-0001"
    return [
        {
            **_source_noop_agent_semantic_judgments()[0],
            "resolved_spans": [
                {
                    "span_ref": f"reading_block_id={block_id};part_index=0",
                    "scope": {"reading_block_id": block_id},
                    "reading_block_id": block_id,
                    "part_index": 0,
                    "role": "manual_region",
                    "text": "source already complete",
                    "covered_object_ids": ["obj-source"],
                }
            ],
        }
    ]


def _persist_source_noop_harness_review(prepared: PreparedTemplateTask) -> None:
    harness = prepared.task_root / "work/.docfit/harness"
    harness.mkdir(parents=True, exist_ok=True)
    vocabulary = FieldRegistrySnapshot.load(prepared.registry_source).pre_input_vocabulary()
    (harness / "object-inventory.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "document_sha256": prepared.template_sha256,
                "object_count": 1,
                "reading_block_count": 1,
                "objects": [
                    {
                        "object_id": "obj-source",
                        "type": "paragraph",
                        "locator": "/body/p[1]",
                    }
                ],
                "reading_blocks": [
                    {
                        "block_id": "u-all:block-0001",
                        "range_id": "u-all:range-0001",
                        "unit_id": "u-all",
                        "text": "source already complete",
                        "covered_object_ids": ["obj-source"],
                        "object_text_spans": [
                            {
                                "object_id": "obj-source",
                                "text": "source already complete",
                                "text_start": 0,
                                "text_end": len("source already complete"),
                            }
                        ],
                    }
                ],
                "field_id_vocabulary": vocabulary,
                "field_vocabulary_digest": vocabulary["digest"],
            }
        ),
        encoding="utf-8",
    )
    semantic_judgments = _source_noop_semantic_judgments()
    (harness / "semantic-judgments.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "semantic_judgments_sha256": sha256_json(semantic_judgments),
                "document_sha256": prepared.template_sha256,
                "field_id_vocabulary": vocabulary,
                "field_vocabulary_digest": vocabulary["digest"],
                "judgment_count": 1,
                "covered_object_count": 1,
                "semantic_judgments": semantic_judgments,
            }
        ),
        encoding="utf-8",
    )


def test_prepare_template_cli_exposes_stage_resume_flags() -> None:
    args = build_parser().parse_args(
        [
            "prepare-template",
            "--school-template",
            "school.docx",
            "--field-registry",
            "registry.yaml",
            "--output",
            "task",
            "--until",
            "unit-boundary",
            "--force-rebuild-checkpoint",
            "unit-boundary",
        ]
    )

    assert args.until_stage == "unit-boundary"
    assert args.force_rebuild_checkpoint == "unit-boundary"

    resume_args = build_parser().parse_args(
        [
            "prepare-template",
            "--school-template",
            "school.docx",
            "--field-registry",
            "registry.yaml",
            "--output",
            "task",
            "--from",
            "unit-boundary",
            "--resume-proof",
            "work/.docfit/unit-boundary-checkpoint.json",
        ]
    )

    assert resume_args.from_stage == "unit-boundary"
    assert resume_args.resume_proof == "work/.docfit/unit-boundary-checkpoint.json"

    post_unit_args = build_parser().parse_args(
        [
            "prepare-template",
            "--school-template",
            "school.docx",
            "--field-registry",
            "registry.yaml",
            "--output",
            "task",
            "--from",
            "unit-boundary",
            "--until",
            "post-unit",
        ]
    )

    assert post_unit_args.from_stage == "unit-boundary"
    assert post_unit_args.until_stage == "post-unit"


def test_unit_boundary_checkpoint_is_host_harness_gate_before_main_flow(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)

    checkpoint_prompt = build_unit_boundary_checkpoint_prompt(prepared)
    main_prompt = build_prepare_template_prompt(
        prepared,
        _unit_checkpoint(prepared),
    )
    post_unit_prompt = build_prepare_template_prompt(
        prepared,
        _unit_checkpoint(prepared),
        stop_after_post_unit=True,
    )

    assert "host runtime will run Harness boundary closure before any main preparation flow" in (
        checkpoint_prompt
    )
    assert "Do not call write tools" in checkpoint_prompt
    assert "If school requirements are supplied, Read them before naming units" in (
        checkpoint_prompt
    )
    assert "Do not output slots, deletion reminders" in checkpoint_prompt
    assert "unit_name" in checkpoint_prompt
    assert "focus=document_map" in checkpoint_prompt
    assert "source order and visible boundary text" in checkpoint_prompt
    assert "start_boundary/end_boundary with page when known" in (checkpoint_prompt)
    assert "Do not output low-level document identity" in checkpoint_prompt
    assert "renderer bookkeeping" in checkpoint_prompt
    assert "Tool/Harness code maps your boundary descriptions to Word spans" in (checkpoint_prompt)
    assert "Do not page through object windows just to prove closure" in checkpoint_prompt
    assert "document_map.summary.text_outline is the primary boundary index" in (checkpoint_prompt)
    assert "offset=text_outline_window.next_offset" in checkpoint_prompt
    assert "Do not repeat the same focus/offset window" in checkpoint_prompt
    assert "Return status=complete with summary and units[]" in checkpoint_prompt
    assert "source_hash" not in UNIT_BOUNDARY_OUTPUT_SCHEMA["required"]
    assert "render_ref" not in UNIT_BOUNDARY_OUTPUT_SCHEMA["required"]
    assert "units" not in UNIT_BOUNDARY_OUTPUT_SCHEMA["required"]
    assert "Runtime unit-boundary checkpoint already passed before this main flow" in main_prompt
    assert "Harness, not the Agent, accepted mechanical boundary closure" in main_prompt
    assert "Begin post-unit semantic judgment" in main_prompt
    assert "do not start from final artifact or delivery review" in main_prompt
    assert "Do not call boundary-closure checks" in main_prompt
    assert "resolved_units" in main_prompt
    assert "accepted_units" not in main_prompt
    assert "u-all" in main_prompt
    assert "whether a whole-unit semantic_judgment can close" in main_prompt
    assert "Terminal examples include fixed declarations" in main_prompt
    assert "manual signature/date pages" in main_prompt
    assert "task/proposal forms" in main_prompt
    assert "keep form notes, usage notes" in main_prompt
    assert "do not split form notes into template-note deletion" in main_prompt
    assert "and school review or approval forms" in main_prompt
    assert "generated TOC/list areas" not in main_prompt
    assert "Directory/list units are generated areas rather than unit-layer terminal keeps" in (
        main_prompt
    )
    assert "generated reading_block/range_id semantics" in main_prompt
    assert "TOC/list mechanism, source title families, and inclusion depth" in main_prompt
    assert "not by decomposing old cache rows as content" in main_prompt
    assert "do not decompose the unit just to bind fields or inspect styles" in main_prompt
    assert "focus=unit_evidence_packet and unit_id" in main_prompt
    assert "Agent-readable unit source entry packet" in main_prompt
    assert "field_id_vocabulary, source_entries[].source_entry_id" in main_prompt
    assert "source_entries[].text, reading_blocks as view context" in main_prompt
    assert "summary.reading_ranges[].range_id for whole-unit ranges" in main_prompt
    assert "Use the whole-unit range when one semantic judgment must cover" in main_prompt
    assert "field_id_vocabulary.allowed_field_ids" in main_prompt
    assert "usage_affordance.allowed_part_roles" in main_prompt
    assert "Registry lookup is needed only for automatic field-slot judgments" not in (
        main_prompt
    )
    assert "semantic_field when you only know the judged field meaning" not in main_prompt
    assert "Style context" in main_prompt
    assert "needed only when slot/style inheritance is unclear" in main_prompt
    assert "Terminal whole-unit keeps" in main_prompt
    assert "generated TOC/list judgments" in main_prompt
    assert "semantic_judgments set" in main_prompt
    assert "source_entry_id plus ordered parts" in main_prompt
    assert "source_entry_id from source_entries and an ordered parts array" in (
        main_prompt
    )
    assert "Do not build per-object mechanical gate payloads" in main_prompt
    assert "Harness reviews the completed judgment set" in main_prompt
    assert "Do not call write, render, visual review, or delivery tools" in main_prompt
    assert (
        "After Harness accepts the semantic set, App/Harness code owns deterministic "
        "materialization" in main_prompt
    )
    assert "This run stops at the post-unit checkpoint" in post_unit_prompt
    assert "do not produce final output paths, review handles, page-review lists" in (
        post_unit_prompt
    )
    assert "single post-unit semantic judgment transaction" in post_unit_prompt
    assert "do not delegate" in post_unit_prompt
    assert "Optional subagents" not in post_unit_prompt
    assert "Return complete only with final_docx" not in post_unit_prompt
    assert "candidate_render_ref" not in main_prompt
    assert "reviewed_pages" not in main_prompt
    assert "missing_evidence" not in main_prompt
    assert "action_requirement" not in main_prompt
    assert "action_plan checks" not in main_prompt
    assert "After every docfit_apply, refresh target evidence" not in main_prompt
    assert "copy target_ref exactly" not in main_prompt
    assert "docfit_apply` 前必须把 `payload.units`" not in main_prompt


def test_post_unit_prompt_preloads_special_unit_reference_context(tmp_path: Path) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["resolved_units"] = [
        {
            "unit_id": "u-toc",
            "unit_name": "目录",
            "responsibility": "generated table of contents",
            "start_locator": "/body/p[1]",
            "end_locator": "/body/p[2]",
        },
        {
            "unit_id": "u-body",
            "unit_name": "论文正文",
            "responsibility": "body representative chapter structure",
            "start_locator": "/body/p[3]",
            "end_locator": "/body/p[4]",
        },
    ]

    prompt = build_prepare_template_prompt(
        prepared,
        checkpoint,
        stop_after_post_unit=True,
    )

    assert "Special unit Reference context selected from resolved_units" in prompt
    assert "accepted_units" not in prompt
    assert "generic text classification is only an initial semantic aid" in prompt
    assert "generic text classification is fallback only" not in prompt
    assert "references/generated-content-and-toc.md" in prompt
    assert "目录 unit 下钻先分离固定外壳、真实生成机制、结果样式、可见缓存和来源标题族" in (
        prompt
    )
    assert "### 目录输出结构" in prompt
    assert '"role": "generated_content"' in prompt
    assert "ordinary judgment" in prompt
    assert '"generated_field_id": "generated.toc"' not in prompt
    assert '"source_title_families"' not in prompt
    assert "Generated content and body structure fields must be chosen" in prompt
    assert "field_id_vocabulary" in prompt
    assert "usage_affordance.allowed_part_roles" in prompt
    assert "A TOC generated judgment must include toc_contract" not in prompt
    assert "toc_contract" not in prompt
    assert "references/body-structure.md" in prompt
    assert "正文 unit 下钻先判断正文代表结构" in prompt
    assert "正文代表结构用 scoped ordered `body_structure` parts 表达" in prompt
    assert "`covered_reading_block_ids` 与 `members` 必须按文档顺序一一对应" not in (
        prompt
    )
    assert "candidate_render_ref" not in prompt
    assert "reviewed_pages" not in prompt


def test_until_unit_boundary_writes_checkpoint_without_final_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_checkpoint(prepared: PreparedTemplateTask) -> dict[str, object]:
        checkpoint = _unit_checkpoint(prepared)
        (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
            json.dumps(checkpoint),
            encoding="utf-8",
        )
        return checkpoint

    monkeypatch.setattr(
        "docfit.app.prepare_template.run_unit_boundary_checkpoint",
        fake_checkpoint,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._validate_unit_boundary_checkpoint",
        lambda _prepared, checkpoint: checkpoint,
    )

    report = asyncio.run(run_prepare_template(_request(tmp_path, until_stage="unit-boundary")))

    assert report.status == "checkpointed"
    assert report.counts == {"checkpoint": "unit-boundary", "unit_count": 1}
    assert not (Path(report.task_root) / "output/final-template.docx").exists()
    checkpoint = json.loads(
        (Path(report.task_root) / "work/.docfit/unit-boundary-checkpoint.json").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["status"] == "ok"
    trace = json.loads(
        (Path(report.task_root) / "work/.docfit/template-agent-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["agent_completion"]["status"] == "checkpointed"


def test_unit_boundary_checkpoint_payload_names_checkpoint_stage(tmp_path: Path) -> None:
    prepared = _prepared(tmp_path)

    checkpoint = _unit_boundary_checkpoint_payload(
        prepared=prepared,
        backend=type("Backend", (), {"name": "test"})(),
        structured_output={
            "summary": "Accepted one synthetic top-level unit.",
            "units": [
                {
                    "unit_id": "u-all",
                    "unit_name": "source",
                    "start_boundary": {"page": 1, "seen_text": "start"},
                    "end_boundary": {"page": 1, "seen_text": "end"},
                }
            ],
            "resolved_units": [
                {
                    "unit_id": "u-all",
                    "unit_name": "source",
                    "start_locator": "/body/p[1]",
                    "end_locator": "/body/p[1]",
                }
            ],
        },
        tool_uses=("Skill", "mcp__docfit__docfit_evidence"),
        skills_loaded=("docfit-school-extract",),
        permission_events=(),
        session_id="unit-session",
        sdk_query_count=1,
        harness_feedback_attempts=0,
        wall_duration_ms=5,
        timing_events=(
            {
                "schema_version": "docfit-timing-event/v1",
                "stage": "unit-boundary",
                "operation": "sdk_query",
                "query_index": 1,
                "started_elapsed_ms": 0,
                "ended_elapsed_ms": 5,
                "duration_ms": 5,
                "status": "response_complete",
            },
        ),
    )

    assert checkpoint["checkpoint"] == "unit-boundary"
    assert checkpoint["resolved_units"] == [
        {
            "unit_id": "u-all",
            "unit_name": "source",
            "start_locator": "/body/p[1]",
            "end_locator": "/body/p[1]",
        }
    ]
    assert checkpoint["timing_events"][0]["operation"] == "sdk_query"
    assert checkpoint["timing_summary"]["by_operation"]["sdk_query"] == {
        "count": 1,
        "duration_ms": 5,
    }


def test_post_unit_inventory_keeps_blank_layout_extent_outside_text_reading_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["resolved_units"] = [
        {
            "unit_id": "u-cover",
            "unit_name": "封面",
            "start_locator": "/body/p[1]",
            "end_locator": "/body/p[3]",
            "covered_object_ids": ["p1", "p2", "p3"],
        }
    ]

    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "标题",
            "object_ref": {"object_id": "p1"},
        },
        {
            "type": "paragraph",
            "locator": "/body/p[2]",
            "text": "",
            "object_ref": {"object_id": "p2"},
        },
        {
            "type": "paragraph",
            "locator": "/body/p[3]",
            "text": "学生姓名",
            "object_ref": {"object_id": "p3"},
        },
    ]
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        lambda _service, _args: {
            "objects": objects,
            "document": {"sha256": prepared.template_sha256},
        },
    )

    inventory = _post_unit_inventory_from_checkpoint(prepared, checkpoint)

    assert [item["text"] for item in inventory["reading_blocks"]] == ["标题", "学生姓名"]
    assert [
        item["object_ref"]["object_id"] for item in inventory["objects"]
    ] == ["p1", "p2", "p3"]
    blank_entry = next(
        entry
        for entry in inventory["source_entries"]
        if entry["provenance"][0]["object_id"] == "p2"
    )
    assert blank_entry["extent"] == {"kind": "whole_entry"}
    assert blank_entry["provenance"][0]["extent"] == {"kind": "whole_entry"}
    assert "field_id_vocabulary" in inventory


def test_post_unit_inventory_builds_source_entries_before_reading_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["resolved_units"] = [
        {
            "unit_id": "u-cover",
            "unit_name": "封面",
            "start_locator": "/body/p[1]",
            "end_locator": "/body/p[1]",
        }
    ]

    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "姓名：张三",
            "object_ref": {
                "object_id": "obj-paragraph",
                "expected_fingerprint": "a" * 64,
            },
        },
        {
            "type": "run",
            "locator": "/body/p[1]/r[1]",
            "text": "姓名：",
            "object_ref": {
                "object_id": "obj-label",
                "expected_fingerprint": "b" * 64,
            },
        },
        {
            "type": "run",
            "locator": "/body/p[1]/r[2]",
            "text": "张三",
            "object_ref": {
                "object_id": "obj-value",
                "expected_fingerprint": "c" * 64,
            },
        },
    ]
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        lambda _service, _args: {
            "objects": objects,
            "document": {"sha256": prepared.template_sha256},
        },
    )

    inventory = _post_unit_inventory_from_checkpoint(prepared, checkpoint)

    assert len(inventory["source_entries"]) == 1
    source_entry = inventory["source_entries"][0]
    source_entry_id = source_entry["source_entry_id"]
    assert source_entry["text"] == "姓名：张三"
    assert [item["object_id"] for item in source_entry["provenance"]] == [
        "obj-paragraph",
        "obj-label",
        "obj-value",
    ]
    assert [item["source_entry_id"] for item in inventory["objects"]] == [
        source_entry_id,
        source_entry_id,
        source_entry_id,
    ]
    reading_block = inventory["reading_blocks"][0]
    assert reading_block["covered_source_entry_ids"] == [source_entry_id]
    assert reading_block["source_entry_text_spans"] == [
        {
            "text_start": 0,
            "text_end": 3,
            "text": "姓名：",
            "source_entry_id": source_entry_id,
        },
        {
            "text_start": 3,
            "text_end": 5,
            "text": "张三",
            "source_entry_id": source_entry_id,
        },
    ]


def test_post_unit_inventory_is_built_once_and_reused_on_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    calls = 0
    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "  标题\n副标题  ",
            "object_ref": {
                "document_sha256": prepared.template_sha256,
                "object_id": "obj-title",
                "expected_fingerprint": "a" * 64,
            },
        }
    ]

    def inspect_once(_service: object, _args: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "objects": objects,
            "document": {"sha256": prepared.template_sha256},
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        inspect_once,
    )

    first = _ensure_post_unit_inventory(prepared, checkpoint)
    retry = _ensure_post_unit_inventory(prepared, checkpoint)

    assert calls == 1
    assert first["canonical_source_inventory"] == retry["canonical_source_inventory"]
    assert first["source_entries"][0]["text"] == "  标题\n副标题  "
    persisted = json.loads(
        (prepared.task_root / "work/.docfit/harness/source-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted == first["canonical_source_inventory"]
    projected_entry = first["unit_reading_packets"]["u-all"]["source_entries"][0]
    assert projected_entry == {
        key: first["source_entries"][0][key]
        for key in ("source_entry_id", "text", "entry_type", "source_order", "extent")
    }


def test_post_unit_inventory_assigns_global_reading_block_order_across_units(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["resolved_units"] = [
        {
            "unit_id": "u-one",
            "unit_name": "第一章",
            "start_locator": "/body/p[1]",
            "end_locator": "/body/p[2]",
        },
        {
            "unit_id": "u-two",
            "unit_name": "第二章",
            "start_locator": "/body/p[3]",
            "end_locator": "/body/p[4]",
        },
    ]

    objects = [
        {
            "type": "paragraph",
            "locator": f"/body/p[{index}]",
            "text": text,
            "object_ref": {"object_id": f"p{index}"},
        }
        for index, text in enumerate(
            ("第一章", "正文一", "第二章", "正文二"),
            start=1,
        )
    ]
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        lambda _service, _args: {
            "objects": objects,
            "document": {"sha256": prepared.template_sha256},
        },
    )

    inventory = _post_unit_inventory_from_checkpoint(prepared, checkpoint)

    assert [block["order"] for block in inventory["reading_blocks"]] == [1, 2, 3, 4]
    assert [block["range_id"] for block in inventory["reading_blocks"]] == [
        "u-one:range-0001",
        "u-one:range-0002",
        "u-two:range-0001",
        "u-two:range-0002",
    ]
    assert [block["unit_range_id"] for block in inventory["reading_blocks"]] == [
        "u-one:range-whole-unit",
        "u-one:range-whole-unit",
        "u-two:range-whole-unit",
        "u-two:range-whole-unit",
    ]


def test_post_unit_inventory_rejects_legacy_scope_ref_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["resolved_units"] = [
        {
            "unit_id": "u-all",
            "unit_name": "source",
            "scope_ref": "/body/p[1]",
        }
    ]
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        lambda _service, _args: {
            "objects": [],
            "document": {"sha256": prepared.template_sha256},
        },
    )

    with pytest.raises(ToolFailure) as caught:
        _post_unit_inventory_from_checkpoint(prepared, checkpoint)

    error = caught.value
    assert error.code == "post_unit_inventory_range_missing"
    assert "scope_ref" not in error.message
    assert "locator" not in error.message
    assert "checkpoint" not in error.message
    assert all("scope_ref" not in action for action in error.suggested_actions)
    assert all("locator" not in action for action in error.suggested_actions)
    assert all("checkpoint" not in action for action in error.suggested_actions)


def test_post_unit_inventory_rejects_legacy_checkpoint_unit_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["accepted_units"] = checkpoint["resolved_units"]
    checkpoint.pop("resolved_units")
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        lambda _service, _args: {
            "objects": [],
            "document": {"sha256": prepared.template_sha256},
        },
    )

    with pytest.raises(ToolFailure) as caught:
        _post_unit_inventory_from_checkpoint(prepared, checkpoint)

    error = caught.value
    assert error.code == "post_unit_inventory_units_missing"
    assert "resolved_units" in error.message


def test_post_unit_inventory_rejects_resolved_unit_without_unit_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["resolved_units"] = [
        {
            "unit_name": "source",
            "start_locator": "/body/p[1]",
            "end_locator": "/body/p[1]",
        }
    ]
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        lambda _service, _args: {
            "objects": [],
            "document": {"sha256": prepared.template_sha256},
        },
    )

    with pytest.raises(ToolFailure) as caught:
        _post_unit_inventory_from_checkpoint(prepared, checkpoint)

    error = caught.value
    assert error.code == "post_unit_inventory_unit_invalid"
    assert "unit_id" in error.message


def test_unit_boundary_checkpoint_records_per_query_timing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    queries: list[str] = []
    checks: list[dict[str, object]] = [
        {
            "status": "needs_input",
            "feedback": {"type": "unit_coverage"},
            "blockers": [{"code": "ambiguous_boundary"}],
        },
        {
            "status": "ok",
            "resolved_units": [
                {
                    "unit_id": "u-all",
                    "unit_name": "source",
                    "start_locator": "/body/p[1]",
                    "end_locator": "/body/p[1]",
                }
            ],
        },
    ]
    check_args: list[dict[str, object]] = []

    class ScriptedBoundaryClient:
        def __init__(self, *, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> ScriptedBoundaryClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self) -> Any:
            query_count = len(queries)
            yield ResultMessage(
                subtype="success",
                duration_ms=11,
                duration_api_ms=7,
                is_error=False,
                num_turns=query_count,
                session_id="unit-session",
                result="{}",
                structured_output={
                    "status": "complete",
                    "summary": f"boundary pass {query_count}",
                    "units": [
                        {
                            "unit_id": "u-all",
                            "unit_name": "source",
                            "start_boundary": {"page": 1, "seen_text": "start"},
                            "end_boundary": {"page": 1, "seen_text": "end"},
                        }
                    ],
                },
                uuid=f"unit-result-{query_count}",
            )

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", ScriptedBoundaryClient)

    def fake_check(_service: object, args: dict[str, object]) -> dict[str, object]:
        check_args.append(dict(args))
        return checks.pop(0)

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        fake_check,
    )

    checkpoint = asyncio.run(
        _run_unit_boundary_checkpoint(
            prepared,
            _backend(),
            config,
        )
    )

    assert checkpoint["status"] == "ok"
    assert len(check_args) == 2
    assert all("source_hash" not in args for args in check_args)
    assert checkpoint["sdk_query_count"] == 2
    assert checkpoint["harness_feedback_attempts"] == 1
    assert len(queries) == 2
    assert queries[1].startswith("DocFit unit-boundary checkpoint v1")
    assert "Runtime Harness feedback" in queries[1]
    assert [event["operation"] for event in checkpoint["timing_events"]] == [
        "sdk_query",
        "harness_feedback_check",
        "sdk_query",
        "harness_feedback_check",
    ]
    sdk_query_events = [
        event for event in checkpoint["timing_events"] if event["operation"] == "sdk_query"
    ]
    assert [event["prompt_kind"] for event in sdk_query_events] == [
        "initial",
        "harness_feedback",
    ]
    feedback_events = [
        event
        for event in checkpoint["timing_events"]
        if event["operation"] == "harness_feedback_check"
    ]
    assert feedback_events[0]["status"] == "needs_feedback"
    assert feedback_events[0]["feedback_type"] == "unit_coverage"
    assert feedback_events[1]["status"] == "accepted"
    assert checkpoint["timing_summary"]["by_operation"]["sdk_query"]["count"] == 2


def test_until_post_unit_writes_semantic_checkpoint_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    checkpoint = _unit_checkpoint(prepared)
    (prepared.task_root / "work/.docfit").mkdir(parents=True, exist_ok=True)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )
    (prepared.task_root / "work/.docfit/post-unit-checkpoint.json").write_text(
        json.dumps(
            {
                "schema_version": "docfit-post-unit-proof/v1",
                "checkpoint": "post-unit",
                "status": "stale",
                "source_hash": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    async def agent_runner(_prepared: PreparedTemplateTask) -> TemplateAgentExecution:
        return TemplateAgentExecution(
            structured_output={
                "status": "complete",
                "summary": "post-unit semantics accepted",
                "semantic_judgments": _source_noop_agent_semantic_judgments(),
            },
            tool_uses=("Skill", "mcp__docfit__docfit_evidence"),
            skills_loaded=("docfit-school-extract",),
            session_id="post-unit-session",
            backend="test",
            num_turns=1,
            duration_ms=10,
            duration_api_ms=8,
        )

    def fake_semantic_feedback(
        checked: PreparedTemplateTask,
        _output: dict[str, object],
    ) -> dict[str, object] | None:
        _persist_source_noop_harness_review(checked)
        return None

    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        fake_semantic_feedback,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        lambda _prepared: None,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        lambda _service, _args: {
            "status": "ok",
            "unit_count": 1,
            "resolved_units": checkpoint["resolved_units"],
        },
    )

    report = asyncio.run(
        run_prepare_template(
            _request(
                tmp_path,
                output_directory=prepared.task_root,
                from_stage="unit-boundary",
                until_stage="post-unit",
            ),
            agent_runner=agent_runner,
        )
    )

    assert report.status == "checkpointed"
    assert report.counts == {
        "checkpoint": "post-unit",
        "object_count": 1,
        "reading_block_count": 1,
        "judgment_count": 1,
        "covered_object_count": 1,
    }
    assert not (prepared.task_root / "output/final-template.docx").exists()
    post_unit = json.loads(
        (prepared.task_root / "work/.docfit/post-unit-checkpoint.json").read_text(encoding="utf-8")
    )
    assert post_unit["checkpoint"] == "post-unit"
    assert post_unit["status"] == "ok"
    assert post_unit["semantic_judgments"] == "work/.docfit/harness/semantic-judgments.json"
    trace = json.loads(
        (prepared.task_root / "work/.docfit/template-agent-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["agent_completion"]["summary"] == "post-unit semantics accepted"
    assert "publication" not in trace
    host_events = [
        event
        for event in trace["timing_events"]
        if event["stage"] in {"host-post-agent", "post-unit"}
    ]
    assert [event["operation"] for event in host_events] == [
        "input_integrity_check",
        "post_unit_checkpoint_report",
    ]
    assert trace["timing_summary"]["by_stage"]["host-post-agent"]["count"] == 1


def test_post_unit_checkpoint_fails_closed_on_materialization_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    checkpoint = _unit_checkpoint(prepared)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )

    async def agent_runner(_prepared: PreparedTemplateTask) -> TemplateAgentExecution:
        return TemplateAgentExecution(
            structured_output={
                "status": "complete",
                "summary": "post-unit semantics still need materialization revision",
                "semantic_judgments": _source_noop_agent_semantic_judgments(),
            },
            tool_uses=("Skill", "mcp__docfit__docfit_evidence"),
            skills_loaded=("docfit-school-extract",),
            session_id="post-unit-session",
            backend="test",
            num_turns=1,
            duration_ms=10,
            duration_api_ms=8,
        )

    def fake_semantic_feedback(
        checked: PreparedTemplateTask,
        _output: dict[str, object],
    ) -> dict[str, object] | None:
        _persist_source_noop_harness_review(checked)
        return None

    def fake_readiness_feedback(_prepared: PreparedTemplateTask) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": "needs_input",
            "feedback": {"type": "materialization_readiness"},
            "blockers": [
                {
                    "code": "materialization_body_structure_candidate_ambiguous",
                    "judgment_id": "j-body",
                    "evidence_focus": "unit_evidence_packet",
                    "missing_requirement": "single_contiguous_body_structure_candidate",
                    "message": "Body structure candidate selection is ambiguous.",
                },
                {
                    "code": "materialization_semantic_judgment_unresolved",
                    "judgment_id": "j-body-open",
                    "evidence_focus": "unit_evidence_packet",
                    "missing_requirement": "open_questions",
                    "message": "raw open question message",
                },
                {
                    "code": "materialization_slot_field_incompatible",
                    "judgment_id": "j-appendix-slot",
                    "evidence_focus": "field_id_vocabulary",
                    "missing_requirement": "field_id_vocabulary.fillable_leaf_field_id",
                    "field_id": "body.paragraph",
                    "message": "generic incompatible field message",
                },
                {
                    "code": "materialization_slot_field_missing",
                    "judgment_id": "j-keywords",
                    "evidence_focus": "field_id_vocabulary",
                    "missing_requirement": "registry_field",
                    "message": "raw slot field missing",
                },
                {
                    "code": "materialization_part_field_missing",
                    "judgment_id": "j-keywords",
                    "evidence_focus": "field_id_vocabulary",
                    "missing_requirement": "parts[].field_id",
                    "message": (
                        "This executable ordered part is missing field_id from the "
                        "pre-input field vocabulary."
                    ),
                },
                {
                    "code": "materialization_body_structure_semantics_missing",
                    "judgment_id": "j-references",
                    "evidence_focus": "unit_evidence_packet",
                    "missing_requirement": "structure_ref, members",
                    "message": "raw body structure missing",
                },
                {
                    "code": "materialization_body_structure_range_group_missing",
                    "judgment_id": "j-body-fragmented",
                    "evidence_focus": "unit_evidence_packet",
                    "missing_requirement": "single_scoped_body_structure_range",
                    "message": "raw body structure range grouping missing",
                },
                {
                    "code": "materialization_object_text_spans_missing",
                    "judgment_id": "j-internal-span-ledger",
                    "evidence_focus": "unit_evidence_packet",
                    "missing_requirement": "object_text_spans",
                    "message": "object_text_spans leaked from Harness internals",
                },
            ],
            "failure": {
                "code": "template_materialization_readiness_incomplete",
                "message": "Accepted semantic_judgments are not ready.",
                "suggested_actions": ["return_to_agent_with_materialization_readiness_feedback"],
            },
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        fake_semantic_feedback,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        lambda _service, _args: {
            "status": "ok",
            "unit_count": 1,
            "resolved_units": checkpoint["resolved_units"],
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        fake_readiness_feedback,
    )

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(
            run_prepare_template(
                _request(
                    tmp_path,
                    output_directory=prepared.task_root,
                    from_stage="unit-boundary",
                    until_stage="post-unit",
                ),
                agent_runner=agent_runner,
            )
        )

    assert caught.value.code == "template_materialization_readiness_incomplete"
    assert not (prepared.task_root / "work/.docfit/post-unit-checkpoint.json").exists()
    receipt = json.loads(
        (
            prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "needs_input"
    packet_text = json.dumps(receipt["agent_revision_packet"], ensure_ascii=False)
    for legacy_token in (
        "judgment_id",
        "registry_field",
        "semantic_field",
        "semantic_parts",
        "covered_reading_block_ids",
        "covered_reading_range_ids",
        "covered_reading_spans",
        "structure_ref",
        "members",
        "required_field_ids",
        "bound_field_ids",
        "toc_contract",
        "generated_field_id",
        "variant_id",
        "variant_role",
        "object_text_spans",
    ):
        assert legacy_token not in packet_text
    assert (
        receipt["agent_revision_packet"]["affected"][0]["code"]
        == "body_structure_parts_incomplete"
    )
    assert (
        receipt["agent_revision_packet"]["affected"][0]["missing_requirement"]
        == "body_structure_parts"
    )
    assert (
        receipt["agent_revision_packet"]["affected"][0]["evidence_focus"] == "unit_evidence_packet"
    )
    assert "contiguous body track" in receipt["agent_revision_packet"]["affected"][0]["message"]
    assert (
        receipt["agent_revision_packet"]["affected"][1]["code"]
        == "materialization_semantic_judgment_unresolved"
    )
    assert (
        receipt["agent_revision_packet"]["affected"][1]["evidence_focus"] == "unit_evidence_packet"
    )
    assert (
        "complete semantic_judgment cannot keep open_questions"
        in (receipt["agent_revision_packet"]["affected"][1]["message"])
    )
    assert (
        receipt["agent_revision_packet"]["affected"][2]["evidence_focus"]
        == "field_id_vocabulary"
    )
    assert receipt["agent_revision_packet"]["affected"][2]["field_id"] == "body.paragraph"
    assert (
        "cannot be used as a plain fillable slot"
        in (receipt["agent_revision_packet"]["affected"][2]["message"])
    )
    affected = receipt["agent_revision_packet"]["affected"]
    by_identity = {
        item.get("code"): item
        for item in affected
        if isinstance(item, dict)
    }
    slot_missing = by_identity["materialization_slot_field_missing"]
    assert "field_id from the pre-input field_id_vocabulary" in slot_missing["message"]
    assert "First call docfit_evidence with focus=registry_field" not in (
        slot_missing["message"]
    )
    part_missing = by_identity["materialization_part_field_missing"]
    assert "executable ordered part is missing field_id" in part_missing["message"]
    assert part_missing["missing_requirement"] == "parts[].field_id"
    body_missing = by_identity["materialization_body_structure_semantics_missing"]
    assert "actual body representative" in body_missing["message"]
    assert "ordered body_structure parts" in body_missing["message"]
    assert body_missing["evidence_focus"] == "unit_evidence_packet"
    body_group_missing = by_identity["body_structure_parts_incomplete"]
    assert body_group_missing["missing_requirement"] == "body_structure_parts"
    assert "contiguous body track" in body_group_missing["message"]
    assert "Word carrier" in receipt["agent_revision_packet"]["next_step"]


def test_existing_post_unit_checkpoint_publishes_without_agent_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    unit_checkpoint = _unit_checkpoint(prepared)
    docfit_root = prepared.task_root / "work/.docfit"
    (docfit_root / "unit-boundary-checkpoint.json").write_text(
        json.dumps(unit_checkpoint),
        encoding="utf-8",
    )
    _persist_source_noop_harness_review(prepared)
    (docfit_root / "post-unit-checkpoint.json").write_text(
        json.dumps(
            {
                "schema_version": "docfit-post-unit-proof/v1",
                "checkpoint": "post-unit",
                "status": "ok",
                "source_hash": prepared.template_sha256,
                "summary": "post-unit semantics accepted",
                "backend": "test",
                "session_id": "post-unit-session",
                "tool_uses": ["Skill", "StructuredOutput"],
                "skills_loaded": ["docfit-school-extract"],
            }
        ),
        encoding="utf-8",
    )
    shutil.rmtree(prepared.task_root / "output")

    async def fail_agent_runner(_prepared: PreparedTemplateTask) -> TemplateAgentExecution:
        raise AssertionError("post-unit checkpoint should publish without rerunning Agent")

    def fail_semantic_coverage(
        _prepared: PreparedTemplateTask,
        _output: dict[str, object],
    ) -> dict[str, object] | None:
        raise AssertionError("post-unit checkpoint already accepted semantic coverage")

    def fake_publish(
        *,
        task_root: Path,
        source_docx: Path,
        candidate_docx: Path,
        field_registry: Path,
        validation: dict[str, object],
        visual_review: dict[str, object],
        allow_no_slots: bool = False,
    ) -> dict[str, object]:
        del source_docx, field_registry, validation, visual_review, allow_no_slots
        output = task_root / "output/final-template.docx"
        contract = task_root / "output/fill-contract.yaml"
        output.parent.mkdir(exist_ok=True)
        shutil.copyfile(candidate_docx, output)
        contract.write_text("schema_version: test\n", encoding="utf-8")
        return {
            "status": "ok",
            "published": True,
            "artifact_path": "output/final-template.docx",
            "fill_contract_path": "output/fill-contract.yaml",
            "template_sha256": sha256_file(output),
            "counts": {"manual": 1},
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.validate",
        lambda _service, _args: {"status": "ok", "checks": []},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {"status": "needs_input", "failure": {"message": "no slots"}},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        fail_semantic_coverage,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        lambda _prepared: None,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publish_template_artifact",
        fake_publish,
    )

    report = asyncio.run(
        run_prepare_template(
            _request(tmp_path, output_directory=prepared.task_root),
            agent_runner=fail_agent_runner,
        )
    )

    assert report.status == "built"
    assert report.counts == {"manual": 1}
    trace = json.loads(
        (prepared.task_root / "work/.docfit/template-agent-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["agent_completion"]["summary"] == "post-unit semantics accepted"
    assert trace["publication"]["published"] is True


def test_host_candidate_selection_rejects_cleanup_only_legacy_materialization_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    assert request.field_registry is not None
    request.field_registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
            )
        ),
        encoding="utf-8",
    )
    prepared = prepare_template_task(request)
    harness = prepared.task_root / "work/.docfit/harness"
    harness.mkdir(parents=True)
    (harness / "object-inventory.json").write_text(
        json.dumps(
            {
                "document_sha256": prepared.template_sha256,
                "objects": [{"object_id": "obj-1", "type": "paragraph"}],
                "reading_blocks": [
                    {
                        "block_id": "u-note:block-0001",
                        "covered_object_ids": ["obj-1"],
                        "text": "模板格式说明行",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (harness / "semantic-judgments.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "semantic_judgments_sha256": "f" * 64,
                "document_sha256": prepared.template_sha256,
                "judgment_count": 1,
                "covered_object_count": 1,
                "semantic_judgments": [
                    {
                        "judgment_id": "j-template-note",
                        "judgment": "old visible template note",
                        "semantic_role": "template_format_instruction",
                        "clean_template_treatment": "delete",
                        "cleanup_reason": "old visible template instruction",
                        "covered_reading_block_ids": ["u-note:block-0001"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has old generated cache"},
        },
    )

    with pytest.raises(ToolFailure) as caught:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert caught.value.code == "template_materialization_semantics_invalid"
    candidate = (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    )
    assert not candidate.exists()
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
    ).exists()


def test_host_candidate_selection_rejects_legacy_review_without_ordered_parts(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    assert request.field_registry is not None
    request.field_registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: advisor.name.en",
                "    label: 导师英文姓名",
                "    content_type: text",
            )
        ),
        encoding="utf-8",
    )
    prepared = prepare_template_task(request)
    harness = prepared.task_root / "work/.docfit/harness"
    harness.mkdir(parents=True)
    (harness / "object-inventory.json").write_text(
        json.dumps(
            {
                "document_sha256": prepared.template_sha256,
                "objects": [{"object_id": "obj-tutor", "type": "run"}],
                "reading_blocks": [
                    {
                        "block_id": "u-paper-body:block-0013",
                        "range_id": "u-paper-body:range-0013",
                        "unit_id": "u-paper-body",
                        "covered_object_ids": ["obj-tutor"],
                        "text": "Tutor:××××",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (harness / "semantic-judgments.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "semantic_judgments_sha256": "f" * 64,
                "document_sha256": prepared.template_sha256,
                "judgment_count": 1,
                "covered_object_count": 1,
                "semantic_judgments": [
                    {
                        "judgment_id": "jd-011",
                        "judgment": (
                            "Tutor: is a fixed English label and ×××× is the "
                            "advisor name placeholder."
                        ),
                        "semantic_role": "fill_slot",
                        "clean_template_treatment": "convert_to_field_slot",
                        "registry_field": "advisor.name.en",
                        "covered_reading_block_ids": ["u-paper-body:block-0013"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolFailure) as caught:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert caught.value.code == "template_materialization_semantics_invalid"
    materialization_dir = prepared.task_root / "work/.docfit/post-unit-materialization"
    assert not (materialization_dir / "candidate-0001.docx").exists()
    assert not (materialization_dir / "materialization.json").exists()


def test_host_candidate_selection_rejects_resolved_span_field_without_part_field(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    _persist_source_noop_harness_review(prepared)
    review_path = prepared.task_root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["semantic_judgments"][0]["resolved_spans"][0]["field_id"] = "author.name.zh"
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review_path.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(ToolFailure) as caught:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert caught.value.code == "template_materialization_semantics_invalid"
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


@pytest.mark.parametrize(
    "span_patch",
    (
        {"text": "source was rewritten after Agent judgment"},
        {"role": "fill_slot"},
    ),
)
def test_host_candidate_selection_rejects_resolved_span_part_mismatch(
    tmp_path: Path,
    span_patch: dict[str, object],
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    _persist_source_noop_harness_review(prepared)
    review_path = prepared.task_root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["semantic_judgments"][0]["resolved_spans"][0].update(span_patch)
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review_path.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(ToolFailure) as caught:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert caught.value.code == "template_materialization_semantics_invalid"
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


def test_host_candidate_selection_rejects_resolved_span_objects_outside_scope(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    _persist_source_noop_harness_review(prepared)
    review_path = prepared.task_root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["semantic_judgments"][0]["resolved_spans"][0]["covered_object_ids"] = [
        "obj-outside-scope"
    ]
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review_path.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(ToolFailure) as caught:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert caught.value.code == "template_materialization_semantics_invalid"
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


def test_host_candidate_selection_rejects_resolved_span_missing_scope_objects(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    _persist_source_noop_harness_review(prepared)
    inventory_path = prepared.task_root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["object_count"] = 2
    inventory["objects"].append(
        {
            "object_id": "obj-unresolved",
            "type": "run",
            "locator": "/body/p[1]/r[2]",
        }
    )
    inventory["reading_blocks"][0]["covered_object_ids"].append("obj-unresolved")
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ToolFailure) as caught:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert caught.value.code == "template_materialization_semantics_invalid"
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


def test_host_candidate_selection_allows_span_covering_text_object_not_carrier(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    _persist_source_noop_harness_review(prepared)
    inventory_path = prepared.task_root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["object_count"] = 2
    inventory["objects"] = [
        {
            "object_id": "obj-carrier",
            "type": "paragraph",
            "locator": "/body/p[1]",
        },
        {
            "object_id": "obj-source",
            "type": "run",
            "locator": "/body/p[1]/r[1]",
        },
    ]
    inventory["reading_blocks"][0]["covered_object_ids"] = ["obj-carrier", "obj-source"]
    inventory["reading_blocks"][0]["object_text_spans"] = [
        {
            "object_id": "obj-source",
            "text": "source already complete",
            "text_start": 0,
            "text_end": len("source already complete"),
        }
    ]
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    assert _select_host_candidate_for_accepted_semantics(prepared) == prepared.template_path


def test_from_unit_boundary_uses_existing_proof_without_rerunning_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "docfit.app.prepare_template._ensure_post_unit_inventory",
        lambda _prepared, _checkpoint: {},
    )
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    checkpoint = _unit_checkpoint(prepared)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )
    queries: list[str] = []

    async def fail_checkpoint(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("unit checkpoint should not rerun during --from resume")

    class MainOnlyClient:
        def __init__(self, *, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> MainOnlyClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self) -> Any:
            yield AssistantMessage(
                content=[
                    ToolUseBlock("skill-1", "Skill", {"skill": "docfit-school-extract"}),
                    ToolUseBlock(
                        "evidence-1",
                        "mcp__docfit__docfit_evidence",
                        {
                            "schema_version": "docfit_evidence_input_v1",
                            "focus": "unit_evidence_packet",
                            "unit_id": "u-all",
                        },
                    ),
                ],
                model="synthetic-model",
                message_id="message-main",
                session_id="session-main",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="session-main",
                result="{}",
                structured_output={
                    "status": "complete",
                    "summary": "semantic judgments complete",
                    "semantic_judgments": _source_noop_agent_semantic_judgments(),
                },
                uuid="result-main",
            )

    def fake_publish(
        *,
        task_root: Path,
        source_docx: Path,
        candidate_docx: Path,
        field_registry: Path,
        validation: dict[str, object],
        visual_review: dict[str, object],
        allow_no_slots: bool = False,
    ) -> dict[str, object]:
        del source_docx, field_registry, validation, visual_review, allow_no_slots
        output = task_root / "output/final-template.docx"
        contract = task_root / "output/fill-contract.yaml"
        shutil.copyfile(candidate_docx, output)
        contract.write_text("schema_version: test\n", encoding="utf-8")
        return {
            "status": "ok",
            "published": True,
            "artifact_path": "output/final-template.docx",
            "fill_contract_path": "output/fill-contract.yaml",
            "template_sha256": sha256_file(output),
            "counts": {"fields": 0},
        }

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", MainOnlyClient)
    monkeypatch.setattr(
        "docfit.app.prepare_template._run_unit_boundary_checkpoint",
        fail_checkpoint,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        lambda _service, _args: {
            "status": "ok",
            "unit_count": 1,
            "resolved_units": checkpoint["resolved_units"],
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.validate",
        lambda _service, _args: {"status": "ok", "checks": []},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {"status": "ok", "failure": None},
    )
    def accept_semantic_feedback(
        checked: PreparedTemplateTask,
        _output: dict[str, object],
    ) -> None:
        _persist_source_noop_harness_review(checked)
        return None

    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        accept_semantic_feedback,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        lambda _prepared: None,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publish_template_artifact",
        fake_publish,
    )

    report = asyncio.run(
        run_prepare_template(
            _request(
                tmp_path,
                output_directory=prepared.task_root,
                from_stage="unit-boundary",
            )
        )
    )

    assert report.status == "built"
    assert len(queries) == 1
    assert "Runtime unit-boundary checkpoint already passed before this main flow" in queries[0]
    trace = json.loads(
        (prepared.task_root / "work/.docfit/template-agent-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["unit_boundary_checkpoint"]["source_hash"] == prepared.template_sha256


@pytest.mark.parametrize("generates_content", [True, False], ids=["generation", "heartbeats"])
def test_post_unit_receive_loop_distinguishes_generation_from_heartbeats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    generates_content: bool,
) -> None:
    prepared = _prepared(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    elapsed_seconds = 0.0
    received_result = False
    generated_deltas = (
        {"type": "thinking_delta", "thinking": "synthetic-private-reasoning"},
        {"type": "text_delta", "text": "synthetic-private-answer"},
        {"type": "input_json_delta", "partial_json": "synthetic-private-tool-input"},
    )
    heartbeat_events = (
        {"type": "ping"},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": ""}},
        {
            "type": "content_block_delta",
            "delta": {"type": "signature_delta", "signature": "synthetic-signature"},
        },
    )

    class StreamingClient:
        def __init__(self, *, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> StreamingClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, _prompt: str) -> None:
            return None

        async def receive_response(self) -> Any:
            nonlocal elapsed_seconds, received_result
            # Each generation phase lasts longer than the no-progress budget,
            # while individual chunks arrive well within it. No tools intervene.
            for delta in generated_deltas:
                for chunk_index in range(4):
                    elapsed_seconds += 60
                    yield StreamEvent(
                        uuid=f"stream-{elapsed_seconds}",
                        session_id="session-streaming",
                        event=(
                            {"type": "content_block_delta", "delta": delta}
                            if generates_content
                            else heartbeat_events[chunk_index % len(heartbeat_events)]
                        ),
                    )
            received_result = True
            yield ResultMessage(
                subtype="success",
                duration_ms=int(elapsed_seconds * 1000),
                duration_api_ms=int(elapsed_seconds * 1000),
                is_error=False,
                num_turns=1,
                session_id="session-streaming",
                structured_output={
                    "status": "complete",
                    "summary": "semantic judgments complete",
                    "semantic_judgments": _source_noop_agent_semantic_judgments(),
                },
            )

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", StreamingClient)
    monkeypatch.setattr("docfit.app.prepare_template.time.perf_counter", lambda: elapsed_seconds)
    monkeypatch.setattr(
        "docfit.app.prepare_template.PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS", 180
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._ensure_post_unit_inventory",
        lambda _prepared, _checkpoint: {},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._runtime_feedback_for_complete_output",
        lambda *_args, **_kwargs: (None, False),
    )

    run = _run_backend(
        prepared,
        _backend(),
        config,
        existing_unit_boundary_checkpoint=_unit_checkpoint(prepared),
        stop_after_post_unit=True,
    )
    if not generates_content:
        with pytest.raises(ToolFailure) as caught:
            asyncio.run(run)
        assert caught.value.code == "template_agent_no_progress_timeout"
        assert not received_result
        assert elapsed_seconds == 180
        return

    execution = asyncio.run(run)
    assert received_result
    assert execution.structured_output["status"] == "complete"
    assert execution.wall_duration_ms == 720_000
    assert execution.sdk_query_count == 2  # Existing boundary query plus this post-unit query.
    assert execution.sdk_events[-1]["message_type"] == "ResultMessage"
    assert len(execution.sdk_events) == 13
    events_text = json.dumps(execution.sdk_events)
    for delta in generated_deltas:
        assert all(value not in events_text for key, value in delta.items() if key != "type")


def test_sdk_receive_event_does_not_record_streamed_content() -> None:
    message = StreamEvent(
        uuid="private-stream-id",
        session_id="private-session-id",
        event={
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "synthetic-private-content"},
        },
    )

    assert _sdk_receive_event(message, elapsed_ms=12, stage="post-unit", query_index=2) == {
        "message_type": "StreamEvent",
        "elapsed_ms": 12,
        "stage": "post-unit",
        "query_index": 2,
        "stream_event_type": "content_block_delta",
        "delta_type": "thinking_delta",
    }


def test_from_unit_boundary_fails_with_trace_when_sdk_has_no_business_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "docfit.app.prepare_template._ensure_post_unit_inventory",
        lambda _prepared, _checkpoint: {},
    )
    prepared = prepare_template_task(_request(tmp_path))
    checkpoint = _unit_checkpoint(prepared)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )

    class NoProgressClient:
        def __init__(self, *, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> NoProgressClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, _prompt: str) -> None:
            return None

        async def receive_response(self) -> Any:
            yield AssistantMessage(
                content=[],
                model="synthetic-model",
                message_id="message-empty",
                session_id="session-no-progress",
            )
            await asyncio.sleep(60)

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", NoProgressClient)
    monkeypatch.setattr(
        "docfit.app.prepare_template.PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS",
        10,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        lambda _service, _args: {
            "status": "ok",
            "unit_count": 1,
            "resolved_units": checkpoint["resolved_units"],
        },
    )

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(
            run_prepare_template(
                _request(
                    tmp_path,
                    output_directory=prepared.task_root,
                    from_stage="unit-boundary",
                    until_stage="post-unit",
                )
            )
        )

    assert caught.value.code == "template_agent_no_progress_timeout"
    trace = json.loads(
        (prepared.task_root / "work/.docfit/template-agent-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["failure"]["code"] == "template_agent_no_progress_timeout"
    assert trace["sdk_query_count"] == 2
    assert trace["unit_boundary_checkpoint"]["source_hash"] == prepared.template_sha256
    assert trace["sdk_events"][-1]["message_type"] == "AssistantMessage"
    assert trace["sdk_events"][-1]["content_block_types"] == []
    timed_queries = [
        event for event in trace["timing_events"] if event["operation"] == "sdk_query"
    ]
    assert timed_queries[-1]["status"] == "no_progress_timeout"
    assert timed_queries[-1]["query_index"] == 2
    assert timed_queries[-1]["message_count"] == 1
    assert trace["timing_summary"]["by_operation"]["sdk_query"]["count"] >= 1


def test_from_unit_boundary_routes_phase_review_request_to_harness_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "docfit.app.prepare_template._ensure_post_unit_inventory",
        lambda _prepared, _checkpoint: {},
    )
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    checkpoint = _unit_checkpoint(prepared)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )
    queries: list[str] = []

    class PhaseReviewClient:
        def __init__(self, *, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> PhaseReviewClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self) -> Any:
            yield AssistantMessage(
                content=[
                    ToolUseBlock("skill-1", "Skill", {"skill": "docfit-school-extract"}),
                    ToolUseBlock(
                        "evidence-1",
                        "mcp__docfit__docfit_evidence",
                        {
                            "schema_version": "docfit_evidence_input_v1",
                            "focus": "unit_evidence_packet",
                            "unit_id": "u-all",
                        },
                    ),
                ],
                model="synthetic-model",
                message_id=f"message-{len(queries)}",
                session_id="session-main",
            )
            if len(queries) == 1:
                yield ResultMessage(
                    subtype="success",
                    duration_ms=10,
                    duration_api_ms=8,
                    is_error=False,
                    num_turns=1,
                    session_id="session-main",
                    result="{}",
                        structured_output={
                            "status": "complete",
                            "summary": "semantic judgments submitted",
                            "semantic_judgments": _source_noop_agent_semantic_judgments(),
                        },
                        uuid="result-needs-review",
                    )
            else:
                yield ResultMessage(
                    subtype="success",
                    duration_ms=10,
                    duration_api_ms=8,
                    is_error=False,
                    num_turns=1,
                    session_id="session-main",
                    result="{}",
                        structured_output={
                            "status": "complete",
                            "summary": "semantic judgments complete",
                            "semantic_judgments": _source_noop_agent_semantic_judgments(),
                        },
                        uuid="result-complete",
                    )

    semantic_calls = 0

    def fake_semantic_feedback(
        _prepared: PreparedTemplateTask,
        _output: dict[str, object],
    ) -> dict[str, object] | None:
        nonlocal semantic_calls
        semantic_calls += 1
        if semantic_calls == 1:
            return {
                "status": "needs_input",
                "feedback": {"type": "semantic_completeness", "mechanical": True},
                "blockers": [{"code": "missing_semantic_judgments"}],
                "failure": {
                    "code": "template_semantic_completeness_incomplete",
                    "suggested_actions": [
                        "return_scope_and_ordered_parts_from_current_unit_reading_packet"
                    ],
                },
            }
        _persist_source_noop_harness_review(_prepared)
        return None

    def fake_publish(
        *,
        task_root: Path,
        source_docx: Path,
        candidate_docx: Path,
        field_registry: Path,
        validation: dict[str, object],
        visual_review: dict[str, object],
        allow_no_slots: bool = False,
    ) -> dict[str, object]:
        del source_docx, field_registry, validation, visual_review, allow_no_slots
        output = task_root / "output/final-template.docx"
        contract = task_root / "output/fill-contract.yaml"
        shutil.copyfile(candidate_docx, output)
        contract.write_text("schema_version: test\n", encoding="utf-8")
        return {
            "status": "ok",
            "published": True,
            "artifact_path": "output/final-template.docx",
            "fill_contract_path": "output/fill-contract.yaml",
            "template_sha256": sha256_file(output),
            "counts": {"fields": 0},
        }

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", PhaseReviewClient)
    monkeypatch.setattr(
        "docfit.app.prepare_template._run_unit_boundary_checkpoint",
        lambda *_args, **_kwargs: pytest.fail("unit checkpoint should not rerun"),
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        lambda _service, _args: {
            "status": "ok",
            "unit_count": 1,
            "resolved_units": checkpoint["resolved_units"],
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.validate",
        lambda _service, _args: {"status": "ok", "checks": []},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {"status": "ok", "failure": None},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        fake_semantic_feedback,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        lambda _prepared: None,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publish_template_artifact",
        fake_publish,
    )

    report = asyncio.run(
        run_prepare_template(
            _request(
                tmp_path,
                output_directory=prepared.task_root,
                from_stage="unit-boundary",
            )
        )
    )

    assert report.status == "built"
    assert len(queries) == 2
    assert "Runtime Harness feedback" in queries[1]
    assert "semantic_source_entry_review" in queries[1]
    assert "Some accepted source entries still need a semantic_judgment" in queries[1]
    assert "object_ref" not in queries[1]
    assert "candidate_hash" not in queries[1]
    trace = json.loads(
        (prepared.task_root / "work/.docfit/template-agent-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["semantic_feedback_attempts"] == 1


def test_post_unit_checkpoint_report_sanitizes_semantic_failure_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    execution = TemplateAgentExecution(
        structured_output={
            "status": "complete",
            "summary": "post-unit semantics ready for review",
            "semantic_judgments": _source_noop_agent_semantic_judgments(),
        },
        tool_uses=("Skill", "mcp__docfit__docfit_evidence"),
        skills_loaded=("docfit-school-extract",),
        session_id="post-unit-session",
        backend="test",
        num_turns=1,
        duration_ms=10,
        duration_api_ms=8,
    )

    def fake_semantic_feedback(
        _prepared: PreparedTemplateTask,
        _output: dict[str, object],
    ) -> dict[str, object]:
        return {
            "status": "needs_input",
            "feedback": {"type": "coverage", "mechanical": True},
            "blockers": [
                {
                    "code": "missing_semantic_judgments",
                    "object_ids": ["obj-hidden-from-agent"],
                    "objects": [
                        {
                            "object_id": "obj-hidden-from-agent",
                            "locator": "/body/p[1]/r[1]",
                        }
                    ],
                    "reading_blocks": [
                        {
                            "block_id": "cover:block-0001",
                            "range_id": "cover:range-0001",
                            "covered_object_ids": ["obj-hidden-from-agent"],
                            "text": "附件1 封面基本格式",
                        }
                    ],
                }
            ],
            "failure": {
                "suggested_actions": ["cover_missing_objects=['obj-hidden-from-agent']"]
            },
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        fake_semantic_feedback,
    )

    with pytest.raises(ToolFailure) as caught:
        _post_unit_checkpoint_report(prepared, execution)

    actions_text = str(caught.value.suggested_actions)
    assert caught.value.code == "template_semantic_coverage_incomplete"
    assert "cover:block-0001" in actions_text
    assert "cover:range-0001" in actions_text
    assert "field_id_vocabulary" in actions_text
    assert "cover_missing_objects" not in actions_text
    assert "obj-hidden-from-agent" not in actions_text
    assert "object_id" not in actions_text
    assert "covered_object_ids" not in actions_text
    assert "locator" not in actions_text


def test_from_unit_boundary_semantic_review_accepts_reading_block_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = {
        **_unit_checkpoint(prepared),
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_locator": "/body/p[1]",
                "end_locator": "/body/p[2]",
                "covered_object_ids": ["r-title", "r-signature"],
            }
        ],
    }
    (prepared.task_root / "work/.docfit").mkdir(parents=True, exist_ok=True)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )

    def fake_inspect(_service: object, _args: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "document": {"sha256": prepared.template_sha256},
            "objects": [
                {
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "诚 信 声 明",
                    "object_ref": {"object_id": "p-title"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[1]",
                    "text": "诚 信 声 明",
                    "object_ref": {"object_id": "r-title"},
                },
                {
                    "type": "paragraph",
                    "locator": "/body/p[2]",
                    "text": "毕业论文（设计）作者签名：",
                    "object_ref": {"object_id": "p-signature"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[2]/r[1]",
                    "text": "毕业论文（设计）作者签名：",
                    "object_ref": {"object_id": "r-signature"},
                },
            ],
            "object_count": 4,
            "risks": [],
            "failure": None,
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        fake_inspect,
    )

    feedback = _semantic_coverage_feedback(
        prepared,
        {
            "status": "needs_input",
            "summary": "ready for Harness phase review",
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u-all:block-0001"},
                    "parts": [
                        {
                            "text": "诚 信 声 明",
                            "role": "fixed_label",
                        }
                    ],
                },
                {
                    "scope": {"reading_block_id": "u-all:block-0002"},
                    "parts": [
                        {
                            "text": "毕业论文（设计）作者签名：",
                            "role": "manual_region",
                        }
                    ],
                },
            ],
        },
    )

    assert feedback is None
    stored = json.loads(
        (prepared.task_root / "work/.docfit/harness/semantic-judgments.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["covered_object_count"] == 2
    assert "covered_object_ids" not in stored["semantic_judgments"][0]
    assert stored["semantic_judgments"][0]["resolved_spans"][0]["covered_object_ids"] == [
        "r-title"
    ]
    inventory = json.loads(
        (prepared.task_root / "work/.docfit/harness/object-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert [block["block_id"] for block in inventory["reading_blocks"]] == [
        "u-all:block-0001",
        "u-all:block-0002",
    ]


def test_from_unit_boundary_semantic_review_accepts_source_entry_judgments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = {
        **_unit_checkpoint(prepared),
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_locator": "/body/p[1]",
                "end_locator": "/body/p[1]",
            }
        ],
    }
    (prepared.task_root / "work/.docfit").mkdir(parents=True, exist_ok=True)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )

    def fake_inspect(_service: object, _args: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "document": {"sha256": prepared.template_sha256},
            "objects": [
                {
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "姓名：张三",
                    "object_ref": {
                        "object_id": "obj-paragraph",
                        "expected_fingerprint": "a" * 64,
                    },
                },
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[1]",
                    "text": "姓名：",
                    "object_ref": {
                        "object_id": "obj-label",
                        "expected_fingerprint": "b" * 64,
                    },
                },
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[2]",
                    "text": "张三",
                    "object_ref": {
                        "object_id": "obj-value",
                        "expected_fingerprint": "c" * 64,
                    },
                },
            ],
            "object_count": 3,
            "risks": [],
            "failure": None,
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        fake_inspect,
    )
    inventory = _post_unit_inventory_from_checkpoint(prepared, checkpoint)
    source_entry_id = inventory["source_entries"][0]["source_entry_id"]

    feedback = _semantic_coverage_feedback(
        prepared,
        {
            "status": "complete",
            "summary": "ready for Harness phase review",
            "semantic_judgments": [
                {
                    "source_entry_id": source_entry_id,
                    "parts": [
                        {"text": "姓名：", "role": "fixed_label"},
                        {
                            "text": "张三",
                            "role": "fill_slot",
                            "field_id": "author.name.zh",
                        },
                    ],
                }
            ],
        },
    )

    assert feedback is None
    stored = json.loads(
        (prepared.task_root / "work/.docfit/harness/semantic-judgments.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["covered_source_entry_count"] == 1
    assert stored["resolved_spans"][1]["source_entry_id"] == source_entry_id
    assert stored["resolved_spans"][1]["slot_ref"] == (
        f"source_entry_id={source_entry_id};part_index=1;field_id=author.name.zh"
    )


def test_from_unit_boundary_inventory_collects_all_reading_block_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = {
        **_unit_checkpoint(prepared),
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_locator": "/body/p[1]",
                "end_locator": "/body/p[2]",
            }
        ],
    }
    (prepared.task_root / "work/.docfit").mkdir(parents=True, exist_ok=True)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )

    def fake_inspect(_service: object, _args: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "document": {"sha256": prepared.template_sha256},
            "objects": [
                {
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "诚 信 声 明",
                    "object_ref": {"object_id": "p-title"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[1]",
                    "text": "诚 信 声 明",
                    "object_ref": {"object_id": "r-title"},
                },
                {
                    "type": "paragraph",
                    "locator": "/body/p[2]",
                    "text": "毕业论文（设计）作者签名：",
                    "object_ref": {"object_id": "p-signature"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[2]/r[1]",
                    "text": "毕业论文（设计）作者签名：",
                    "object_ref": {"object_id": "r-signature"},
                },
            ],
            "object_count": 4,
            "risks": [],
            "failure": None,
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        fake_inspect,
    )

    feedback = _semantic_coverage_feedback(
        prepared,
        {
            "status": "complete",
            "summary": "ready for Harness phase review",
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u-all:block-0001"},
                    "parts": [
                        {
                            "text": "诚 信 声 明",
                            "role": "fixed_label",
                        }
                    ],
                },
                {
                    "scope": {"reading_block_id": "u-all:block-0002"},
                    "parts": [
                        {
                            "text": "毕业论文（设计）作者签名：",
                            "role": "manual_region",
                        }
                    ],
                },
            ],
        },
    )

    assert feedback is None
    inventory = json.loads(
        (prepared.task_root / "work/.docfit/harness/object-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["object_ref"]["object_id"] for item in inventory["objects"]] == [
        "p-title",
        "r-title",
        "p-signature",
        "r-signature",
    ]


def test_from_unit_boundary_semantic_review_accepts_whole_unit_terminal_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = {
        **_unit_checkpoint(prepared),
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_locator": "/body/p[1]",
                "end_locator": "/body/p[2]",
                "covered_object_ids": ["r-title", "r-signature"],
            }
        ],
    }
    (prepared.task_root / "work/.docfit").mkdir(parents=True, exist_ok=True)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )

    def fake_inspect(_service: object, _args: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "document": {"sha256": prepared.template_sha256},
            "objects": [
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[1]",
                    "text": "诚 信 声 明",
                    "object_ref": {"object_id": "r-title"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[2]/r[1]",
                    "text": "毕业论文（设计）作者签名：",
                    "object_ref": {"object_id": "r-signature"},
                },
            ],
            "object_count": 2,
            "risks": [],
            "failure": None,
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        fake_inspect,
    )

    feedback = _semantic_coverage_feedback(
        prepared,
        {
            "status": "needs_input",
            "summary": "whole unit terminal ready for Harness phase review",
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u-all:block-0001"},
                    "parts": [
                        {
                            "text": "诚 信 声 明",
                            "role": "fixed_label",
                        }
                    ],
                },
                {
                    "scope": {"reading_block_id": "u-all:block-0002"},
                    "parts": [
                        {
                            "text": "毕业论文（设计）作者签名：",
                            "role": "manual_region",
                        }
                    ],
                }
            ],
        },
    )

    assert feedback is None
    stored = json.loads(
        (prepared.task_root / "work/.docfit/harness/semantic-judgments.json").read_text(
            encoding="utf-8"
        )
    )
    assert "covered_object_ids" not in stored["semantic_judgments"][0]
    assert "covered_object_ids" not in stored["semantic_judgments"][1]
    assert stored["semantic_judgments"][0]["resolved_spans"][0]["covered_object_ids"] == [
        "r-title"
    ]
    assert stored["semantic_judgments"][1]["resolved_spans"][0]["covered_object_ids"] == [
        "r-signature"
    ]


def test_from_unit_boundary_sends_acceptance_prompt_when_phase_review_accepts_on_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "docfit.app.prepare_template._ensure_post_unit_inventory",
        lambda _prepared, _checkpoint: {},
    )
    prepared = prepare_template_task(_request(tmp_path))
    checkpoint = _unit_checkpoint(prepared)
    (prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )
    queries: list[str] = []

    class PhaseReviewClient:
        def __init__(self, *, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> PhaseReviewClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self) -> Any:
            output: dict[str, object]
            yield AssistantMessage(
                content=[
                    ToolUseBlock("skill-1", "Skill", {"skill": "docfit-school-extract"}),
                    ToolUseBlock(
                        "evidence-1",
                        "mcp__docfit__docfit_evidence",
                        {
                            "schema_version": "docfit_evidence_input_v1",
                            "focus": "unit_evidence_packet",
                            "unit_id": "u-all",
                        },
                    ),
                ],
                model="synthetic-model",
                message_id=f"message-{len(queries)}",
                session_id="session-main",
            )
            if len(queries) < 5:
                output = {
                    "status": "complete",
                    "summary": "semantic judgments submitted",
                    "semantic_judgments": _source_noop_agent_semantic_judgments(),
                }
            else:
                output = {
                    "status": "complete",
                    "summary": "semantic judgments complete",
                    "semantic_judgments": _source_noop_agent_semantic_judgments(),
                }
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="session-main",
                result="{}",
                structured_output=output,
                uuid=f"result-{len(queries)}",
            )

    semantic_calls = 0

    def fake_semantic_feedback(
        _prepared: PreparedTemplateTask,
        _output: dict[str, object],
    ) -> dict[str, object] | None:
        nonlocal semantic_calls
        semantic_calls += 1
        if semantic_calls < 5:
            return {
                "status": "needs_input",
                "feedback": {"type": "semantic_completeness", "mechanical": True},
                "blockers": [{"code": f"semantic_gap_{semantic_calls}"}],
                "failure": {
                    "code": "template_semantic_completeness_incomplete",
                    "suggested_actions": [
                        "return_scope_and_ordered_parts_from_current_unit_reading_packet"
                    ],
                },
            }
        _persist_source_noop_harness_review(_prepared)
        return None

    def fake_publish(
        *,
        task_root: Path,
        source_docx: Path,
        candidate_docx: Path,
        field_registry: Path,
        validation: dict[str, object],
        visual_review: dict[str, object],
        allow_no_slots: bool = False,
    ) -> dict[str, object]:
        del source_docx, field_registry, validation, visual_review, allow_no_slots
        output = task_root / "output/final-template.docx"
        contract = task_root / "output/fill-contract.yaml"
        shutil.copyfile(candidate_docx, output)
        contract.write_text("schema_version: test\n", encoding="utf-8")
        return {
            "status": "ok",
            "published": True,
            "artifact_path": "output/final-template.docx",
            "fill_contract_path": "output/fill-contract.yaml",
            "template_sha256": sha256_file(output),
            "counts": {"fields": 0},
        }

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", PhaseReviewClient)
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        lambda _service, _args: {
            "status": "ok",
            "unit_count": 1,
            "resolved_units": checkpoint["resolved_units"],
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.validate",
        lambda _service, _args: {"status": "ok", "checks": []},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {"status": "ok", "failure": None},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        fake_semantic_feedback,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        lambda _prepared: None,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publish_template_artifact",
        fake_publish,
    )

    report = asyncio.run(
        run_prepare_template(
            _request(
                tmp_path,
                output_directory=prepared.task_root,
                from_stage="unit-boundary",
            )
        )
    )

    assert report.status == "built"
    assert len(queries) == 5
    assert "semantic_source_entry_review" in queries[1]
    assert "semantic_source_entry_review" in queries[2]
    assert "semantic_source_entry_review" in queries[3]
    assert "semantic_source_entry_review" in queries[4]
    assert "object_ref" not in queries[1]
    assert "object_ref" not in queries[4]
    trace = json.loads(
        (prepared.task_root / "work/.docfit/template-agent-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["semantic_feedback_attempts"] == 4


def test_resume_proof_source_hash_mismatch_fails_before_coverage_check(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint["source_hash"] = "b" * 64

    with pytest.raises(ToolFailure) as caught:
        _validate_unit_boundary_checkpoint(prepared, checkpoint)

    assert caught.value.code == "unit_boundary_proof_source_mismatch"


def test_resume_proof_validation_does_not_require_agent_render_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint.pop("render_ref", None)

    def fake_check(self: object, args: dict[str, object]) -> dict[str, object]:
        del self
        assert "source_hash" not in args
        payload = args["payload"]
        assert isinstance(payload, dict)
        assert "render_ref" not in payload
        return {
            "status": "ok",
            "unit_count": 1,
            "resolved_units": checkpoint["resolved_units"],
        }

    monkeypatch.setattr("docfit.app.prepare_template.DocFitToolService.check", fake_check)

    normalized = _validate_unit_boundary_checkpoint(prepared, checkpoint)

    assert normalized["status"] == "ok"
    assert normalized["source_hash"] == prepared.template_sha256
    assert "render_ref" not in normalized


def test_resume_proof_rejects_unit_coverage_result_without_resolved_units(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.check",
        lambda _service, _args: {
            "status": "ok",
            "unit_count": 1,
            "units": checkpoint["resolved_units"],
        },
    )

    with pytest.raises(ToolFailure) as caught:
        _validate_unit_boundary_checkpoint(prepared, checkpoint)

    assert caught.value.code == "unit_boundary_proof_invalid"
    assert "resolved_units" in caught.value.message
    assert "units or resolved_units" not in caught.value.message


def test_resume_proof_rejects_legacy_units_only_checkpoint(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    checkpoint = _unit_checkpoint(prepared)
    checkpoint.pop("resolved_units")

    with pytest.raises(ToolFailure) as caught:
        _validate_unit_boundary_checkpoint(prepared, checkpoint)

    assert caught.value.code == "unit_boundary_proof_invalid"
    assert "resolved_units" in caught.value.message
    assert "units or resolved_units" not in caught.value.message


def test_unit_boundary_schema_excludes_internal_processing_fields() -> None:
    unit_schema = UNIT_BOUNDARY_OUTPUT_SCHEMA["properties"]["units"]["items"]

    assert unit_schema["required"] == [
        "unit_id",
        "unit_name",
        "start_boundary",
        "end_boundary",
    ]
    assert unit_schema["additionalProperties"] is False
    assert "start_locator" not in unit_schema["properties"]
    assert "end_locator" not in unit_schema["properties"]
    assert {"start_boundary", "end_boundary"} <= set(unit_schema["properties"])
    assert "source_hash" not in UNIT_BOUNDARY_OUTPUT_SCHEMA["properties"]
    assert "render_ref" not in UNIT_BOUNDARY_OUTPUT_SCHEMA["properties"]
    assert "missing_evidence" not in UNIT_BOUNDARY_OUTPUT_SCHEMA["properties"]
    assert "needs_input" in UNIT_BOUNDARY_OUTPUT_SCHEMA["properties"]
    assert "units" not in UNIT_BOUNDARY_OUTPUT_SCHEMA["required"]
    assert unit_schema["properties"]["start_boundary"]["required"] == [
        "seen_text",
    ]
    assert "responsibility" not in unit_schema["properties"]
    assert "boundary_kind" not in unit_schema["properties"]
    assert "anchor_object_ids" not in unit_schema["properties"]
    assert "style_anchor" not in unit_schema["properties"]
    assert "boundary_note" not in unit_schema["properties"]
