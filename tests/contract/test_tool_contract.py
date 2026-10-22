from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from docfit.tools import (
    AGENT_TOOL_RESULT_MAX_CHARS,
    DOCFIT_TOOLS,
    FULL_TOOL_NAMES,
    LOGICAL_TOOL_NAMES,
    build_docfit_server,
    build_docfit_tools,
    docfit_apply,
    docfit_evidence,
    docx_edit,
    docx_inspect,
    docx_render,
    docx_validate,
    docx_visual_review,
)
from docfit.tools.edit_actions import EDIT_ACTIONS
from docfit.tools.runtime import sha256_file
from tests.support.source_identity import persist_source_identity, source_partition


def test_exact_public_tool_names() -> None:
    assert LOGICAL_TOOL_NAMES == (
        "docfit_evidence",
        "docfit_check",
        "docfit_apply",
        "docx_inspect",
        "docx_edit",
        "docx_render",
        "docx_visual_review",
        "docx_validate",
    )
    assert FULL_TOOL_NAMES == (
        "mcp__docfit__docfit_evidence",
        "mcp__docfit__docfit_check",
        "mcp__docfit__docfit_apply",
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
        "mcp__docfit__docx_validate",
    )
    assert tuple(tool.name for tool in DOCFIT_TOOLS) == LOGICAL_TOOL_NAMES
    assert all(
        getattr(registered.annotations, "maxResultSizeChars", None) == AGENT_TOOL_RESULT_MAX_CHARS
        for registered in DOCFIT_TOOLS
    )
    assert build_docfit_server()["name"] == "docfit"
    assert tuple(tool.name for tool in build_docfit_tools()) == LOGICAL_TOOL_NAMES


def test_server_builder_can_expose_only_the_canonical_agent_surface() -> None:
    assert tuple(tool.name for tool in build_docfit_tools(include_docx_tools=False)) == (
        "docfit_evidence",
        "docfit_check",
        "docfit_apply",
    )
    server = build_docfit_server(include_docx_tools=False)

    assert server["name"] == "docfit"
    assert build_docfit_server(include_docx_tools=True)["name"] == "docfit"


def test_public_tool_schemas_avoid_unsupported_composition_keywords() -> None:
    def nested_values(value: object) -> list[object]:
        if isinstance(value, dict):
            return [value, *(child for item in value.values() for child in nested_values(item))]
        if isinstance(value, list):
            return [child for item in value for child in nested_values(item)]
        return []

    for registered in DOCFIT_TOOLS:
        dictionaries = [
            item for item in nested_values(registered.input_schema) if isinstance(item, dict)
        ]
        assert all(not {"oneOf", "anyOf", "allOf"}.intersection(item) for item in dictionaries)


def test_task_bound_visual_tools_use_the_application_session_root(tmp_path: Path) -> None:
    document = tmp_path / "unsupported.txt"
    document.write_text("not a docx", encoding="utf-8")
    tools = {registered.name: registered for registered in build_docfit_tools(tmp_path)}

    render_result = asyncio.run(
        tools["docx_render"].handler({"input_docx": str(document), "overview": False})
    )

    assert render_result["structuredContent"]["failure"]["code"] == ("unsupported_document_type")


def test_task_bound_tools_reject_agent_selected_root(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    tools = {registered.name: registered for registered in build_docfit_tools(task_root)}

    result = asyncio.run(
        tools["docx_inspect"].handler({"task_root": str(outside), "input_docx": "outside.docx"})
    )

    assert result["structuredContent"]["failure"]["code"] == "task_root_mismatch"


def _object_ref(document_sha256: str, suffix: str) -> dict[str, str]:
    return {
        "document_sha256": document_sha256,
        "object_id": f"obj-{suffix:0>24}",
        "expected_fingerprint": suffix * 64,
    }


def _object_id(suffix: str) -> str:
    return f"obj-{suffix:0>24}"


def _text_span(suffix: str, text: str, *, start: int = 0) -> dict[str, object]:
    return {
        "object_id": _object_id(suffix),
        "text_start": start,
        "text_end": start + len(text),
        "text": text,
    }


def _write_registry(task_root: Path) -> None:
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
            )
        ),
        encoding="utf-8",
    )


def _fixed_block(reading_block_id: str, text: str) -> dict[str, object]:
    return {
        "scope": {"reading_block_id": reading_block_id},
        "parts": [{"role": "fixed_label", "text": text}],
    }


def test_template_harness_rejects_legacy_object_semantic_coverage(
    tmp_path: Path,
) -> None:
    from docfit.template.harness import TemplateHarnessService

    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    harness = TemplateHarnessService(task_root=task_root)
    document_sha256 = __import__("hashlib").sha256(b"synthetic source").hexdigest()

    current = {
        "action": "submit_object_inventory",
        "document_sha256": document_sha256,
        "objects": [
            {
                "type": "run",
                "locator": f"/body/p[{index}]/r[1]",
                "object_ref": _object_ref(document_sha256, str(index)),
            }
            for index in range(1, 6)
        ],
        "reading_blocks": [
            {
                "block_id": f"u:block-{index:04d}",
                "range_id": f"u:range-{index:04d}",
                "text": f"text {index}",
                "covered_object_ids": [f"obj-{index:024d}"],
                "object_text_spans": [_text_span(str(index), f"text {index}")],
            }
            for index in range(1, 6)
        ],
    }
    current.pop("reading_blocks", None)
    current["source_entries"] = [
        {
            "source_entry_id": f"source-entry-{index}",
            "text": "source",
            "entry_type": "text",
            "source_order": {"block": index, "inline": 0},
            "provenance": [
                {
                    "object_id": obj["object_ref"]["object_id"],
                    "object_ref": obj["object_ref"],
                    "locator": obj["locator"],
                    "fingerprint": obj["object_ref"]["expected_fingerprint"],
                    "text_span": [0, 6],
                }
            ],
        }
        for index, obj in enumerate(current["objects"], 1)
    ]
    for index, obj in enumerate(current["objects"], 1):
        obj["source_entry_id"] = f"source-entry-{index}"
    source_partition(current)
    persist_source_identity(task_root, current)
    inventory = harness.handle(current)

    assert inventory["status"] == "ok"
    assert inventory["harness_state"]["missing_semantic_judgment_object_ids"] == [
        "obj-000000000000000000000001",
        "obj-000000000000000000000002",
        "obj-000000000000000000000003",
        "obj-000000000000000000000004",
        "obj-000000000000000000000005",
    ]
    assert (task_root / "work/.docfit/harness/object-inventory.json").is_file()

    incomplete = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "semantic_judgments": [
                {
                    "judgment_id": "j001-first-four-runs",
                    "judgment": "fixed_content",
                    "covered_object_ids": [
                        "obj-000000000000000000000001",
                        "obj-000000000000000000000002",
                        "obj-000000000000000000000003",
                        "obj-000000000000000000000004",
                    ],
                }
            ],
        }
    )

    assert incomplete["status"] == "needs_input"
    assert incomplete["feedback"] == {
        "type": "ordered_semantic_parts",
        "mechanical": True,
        "semantic_authority": False,
        "agent_action": (
            "Revise post-unit output to source_entry_id + ordered parts; "
            "do not use Registry lookup, "
            "legacy field aliases, Agent-authored IDs, or internal span/object refs."
        ),
    }
    assert incomplete["failure"]["code"] == "ordered_semantic_parts_invalid"
    assert any(
        blocker["code"] == "agent_authored_legacy_or_internal_id"
        and "covered_object_ids" in blocker["forbidden_fields"]
        for blocker in incomplete["blockers"]
    )


def test_docx_validate_completion_feedback_reports_page_gaps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from docfit.tools.service import DocFitToolService

    source = tmp_path / "source.docx"
    final = tmp_path / "final.docx"
    source.write_bytes(b"source")
    final.write_bytes(b"final")
    final_hash = sha256_file(final)

    monkeypatch.setattr("docfit.tools.service.validate_docx_package", lambda _path: ())
    monkeypatch.setattr(
        "docfit.tools.service.inspect_document_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(objects=[]),
    )

    class FakeOffice:
        def validate_snapshot(self, _document: Path) -> dict[str, str]:
            return {"detail": "ok"}

        def evidence(self) -> dict[str, str]:
            return {"name": "fake-office"}

    class FakeStore:
        def resolve_render(self, _reference: str):
            return tmp_path, {
                "document_sha256": final_hash,
                "page_count": 3,
                "fidelity": "approximate",
                "renderer": {"name": "libreoffice"},
            }

    service = DocFitToolService(
        task_root=tmp_path,
        office=FakeOffice(),
        visual=SimpleNamespace(store=FakeStore()),
    )

    result = service.validate(
        {
            "source_docx": str(source),
            "final_docx": str(final),
            "candidate_render_ref": "render:v2:" + "0" * 64,
            "visual_review": {
                "document_sha256": final_hash,
                "reviewed_pages": [1, 3, 99],
                "findings": [],
            },
            "required_visual_coverage": "all_final_pages",
        }
    )

    coverage = next(
        check for check in result["checks"] if check["name"] == "visual_review_coverage"
    )
    assert coverage["blocking"] is True
    assert coverage["feedback"]["type"] == "completion"
    assert coverage["evidence"] == {
        "current_visual_snapshot": True,
        "all_final_pages_reviewed": False,
        "page_count": 3,
        "reviewed_pages": [1, 3, 99],
        "missing_pages": [2],
        "unexpected_pages": [99],
        "blocking_findings": 0,
    }


def test_template_harness_rejects_legacy_locator_semantic_coverage(
    tmp_path: Path,
) -> None:
    from docfit.template.harness import TemplateHarnessService

    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    harness = TemplateHarnessService(task_root=task_root)
    document_sha256 = __import__("hashlib").sha256(b"synthetic source").hexdigest()

    current = {
        "action": "submit_object_inventory",
        "document_sha256": document_sha256,
        "objects": [
            {
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "object_ref": _object_ref(document_sha256, "1"),
            },
            {
                "type": "run",
                "locator": "/body/p[1]/r[2]",
                "object_ref": _object_ref(document_sha256, "2"),
            },
            {
                "type": "run",
                "locator": "/body/p[2]/r[1]",
                "object_ref": _object_ref(document_sha256, "3"),
            },
        ],
        "reading_blocks": [
            {
                "block_id": "u:block-0001",
                "range_id": "u:range-0001",
                "text": "first paragraph",
                "covered_object_ids": [
                    "obj-000000000000000000000001",
                    "obj-000000000000000000000002",
                ],
                "object_text_spans": [
                    _text_span("1", "first"),
                    _text_span("2", "paragraph", start=6),
                ],
            },
            {
                "block_id": "u:block-0002",
                "range_id": "u:range-0002",
                "text": "second paragraph",
                "covered_object_ids": ["obj-000000000000000000000003"],
                "object_text_spans": [_text_span("3", "second paragraph")],
            },
        ],
    }
    current.pop("reading_blocks", None)
    current["source_entries"] = [
        {
            "source_entry_id": f"source-entry-{index}",
            "text": "source",
            "entry_type": "text",
            "source_order": {"block": index, "inline": 0},
            "provenance": [
                {
                    "object_id": obj["object_ref"]["object_id"],
                    "object_ref": obj["object_ref"],
                    "locator": obj["locator"],
                    "fingerprint": obj["object_ref"]["expected_fingerprint"],
                    "text_span": [0, 6],
                }
            ],
        }
        for index, obj in enumerate(current["objects"], 1)
    ]
    for index, obj in enumerate(current["objects"], 1):
        obj["source_entry_id"] = f"source-entry-{index}"
    source_partition(current)
    persist_source_identity(task_root, current)
    harness.handle(current)

    legacy = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "semantic_judgments": [
                {
                    "judgment_id": "j001-first-paragraph",
                    "judgment": "fixed title paragraph",
                    "covered_object_locators": ["/body/p[1]"],
                },
                {
                    "judgment_id": "j002-second-paragraph",
                    "judgment": "fillable title value",
                    "covered_object_ids": ["obj-000000000000000000000003"],
                },
            ],
        }
    )

    assert legacy["status"] == "needs_input"
    assert legacy["failure"]["code"] == "ordered_semantic_parts_invalid"
    assert any(
        blocker["code"] == "agent_authored_legacy_or_internal_id"
        and "covered_object_locators" in blocker["forbidden_fields"]
        for blocker in legacy["blockers"]
    )


def test_template_harness_rejects_legacy_locator_ranges(
    tmp_path: Path,
) -> None:
    from docfit.template.harness import TemplateHarnessService

    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    harness = TemplateHarnessService(task_root=task_root)
    document_sha256 = __import__("hashlib").sha256(b"synthetic source").hexdigest()

    current = {
        "action": "submit_object_inventory",
        "document_sha256": document_sha256,
        "objects": [
            {
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "object_ref": _object_ref(document_sha256, "1"),
            },
            {
                "type": "sdt",
                "locator": "/body/p[1]/sdt[@sdtId=1001]",
                "object_ref": _object_ref(document_sha256, "2"),
            },
        ],
        "reading_blocks": [
            {
                "block_id": "u:block-0001",
                "range_id": "u:range-0001",
                "text": "姓名：",
                "covered_object_ids": ["obj-000000000000000000000001"],
                "object_text_spans": [_text_span("1", "姓名：")],
            },
            {
                "block_id": "u:block-0002",
                "range_id": "u:range-0002",
                "text": "【姓名】",
                "covered_object_ids": ["obj-000000000000000000000002"],
                "object_text_spans": [_text_span("2", "【姓名】")],
            },
        ],
    }
    current.pop("reading_blocks", None)
    current["source_entries"] = [
        {
            "source_entry_id": f"source-entry-{index}",
            "text": "source",
            "entry_type": "text",
            "source_order": {"block": index, "inline": 0},
            "provenance": [
                {
                    "object_id": obj["object_ref"]["object_id"],
                    "object_ref": obj["object_ref"],
                    "locator": obj["locator"],
                    "fingerprint": obj["object_ref"]["expected_fingerprint"],
                    "text_span": [0, 6],
                }
            ],
        }
        for index, obj in enumerate(current["objects"], 1)
    ]
    for index, obj in enumerate(current["objects"], 1):
        obj["source_entry_id"] = f"source-entry-{index}"
    source_partition(current)
    persist_source_identity(task_root, current)
    harness.handle(current)

    legacy = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "semantic_judgments": [
                {
                    "judgment_id": "j-cover-line",
                    "judgment": "fixed label and fillable slot in one cover line",
                    "covered_locator_ranges": [
                        {
                            "start_locator": "/body/p[1]",
                            "end_locator": "/body/p[1]/sdt[@sdtId=1001]",
                        }
                    ],
                }
            ],
        }
    )

    assert legacy["status"] == "needs_input"
    assert legacy["failure"]["code"] == "ordered_semantic_parts_invalid"
    assert any(
        blocker["code"] == "agent_authored_legacy_or_internal_id"
        and "covered_locator_ranges" in blocker["forbidden_fields"]
        for blocker in legacy["blockers"]
    )


def test_real_docx_tools_expose_versioned_v2_schemas_without_backend_selector() -> None:
    result = asyncio.run(docx_inspect.handler({}))

    assert result["structuredContent"]["status"] == "needs_input"
    assert result["structuredContent"]["failure"]["origin"] == "request"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert docfit_evidence.input_schema["required"] == ["schema_version", "focus"]
    for registered in (
        docfit_evidence,
        docfit_apply,
        docx_inspect,
        docx_edit,
        docx_render,
        docx_validate,
    ):
        assert registered.input_schema.get("additionalProperties") is False
    render_properties = docx_render.input_schema["properties"]
    assert set(render_properties) == {"input_docx", "overview"}
    assert not {"provider", "backend", "engine"}.intersection(render_properties)
    edit_actions = docx_edit.input_schema["properties"]["operations"]["items"]["properties"][
        "action"
    ]["enum"]
    assert edit_actions == list(EDIT_ACTIONS)
    assert "import_content_objects" in edit_actions
    assert "import_template_sections" not in edit_actions
    edit_operation_properties = docx_edit.input_schema["properties"]["operations"]["items"][
        "properties"
    ]
    assert set(edit_operation_properties) >= {
        "source_docx",
        "source_sha256",
        "source_refs",
        "target_anchor_ref",
        "include_source_final_section_properties",
    }


def test_visual_review_returns_a_native_image_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    assert "oneOf" not in docx_visual_review.input_schema
    assert docx_visual_review.input_schema["required"] == ["render_ref", "mode"]
    assert docx_visual_review.input_schema["properties"]["mode"]["enum"] == [
        "contact_sheet",
        "pages",
        "regions",
        "compare",
    ]

    image = tmp_path / "page.png"
    Image.new("RGB", (16, 16), "blue").save(image)

    class _FakeService:
        def visual_review(self, args):
            assert args["mode"] == "pages"
            return (
                {
                    "schema_version": 2,
                    "status": "ok",
                    "render_ref": args["render_ref"],
                    "evidence": [],
                },
                [image],
            )

    monkeypatch.setattr("docfit.tools.DocFitToolService", _FakeService)

    render_ref = "render:v2:" + "0" * 64
    result = asyncio.run(
        docx_visual_review.handler({"render_ref": render_ref, "mode": "pages", "pages": [1]})
    )
    image_content = next(item for item in result["content"] if item["type"] == "image")

    assert image_content["mimeType"] == "image/png"
    assert base64.b64decode(image_content["data"]).startswith(b"\x89PNG\r\n\x1a\n")
