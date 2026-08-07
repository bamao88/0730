from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from PIL import Image

from docfit.tools import (
    AGENT_TOOL_RESULT_MAX_CHARS,
    DOCFIT_TOOLS,
    FULL_TOOL_NAMES,
    LOGICAL_TOOL_NAMES,
    build_docfit_server,
    build_docfit_tools,
    docx_edit,
    docx_inspect,
    docx_render,
    docx_validate,
    docx_visual_review,
)


def test_exact_public_tool_names() -> None:
    assert LOGICAL_TOOL_NAMES == (
        "docx_inspect",
        "docx_edit",
        "docx_render",
        "docx_visual_review",
        "docx_validate",
    )
    assert FULL_TOOL_NAMES == (
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
        "mcp__docfit__docx_validate",
    )
    assert tuple(tool.name for tool in DOCFIT_TOOLS) == LOGICAL_TOOL_NAMES
    assert all(
        getattr(registered.annotations, "maxResultSizeChars", None)
        == AGENT_TOOL_RESULT_MAX_CHARS
        for registered in DOCFIT_TOOLS
    )
    assert build_docfit_server()["name"] == "docfit"


def test_public_tool_schemas_avoid_unsupported_composition_keywords() -> None:
    def nested_values(value: object) -> list[object]:
        if isinstance(value, dict):
            return [value, *(child for item in value.values() for child in nested_values(item))]
        if isinstance(value, list):
            return [child for item in value for child in nested_values(item)]
        return []

    for registered in DOCFIT_TOOLS:
        dictionaries = [
            item
            for item in nested_values(registered.input_schema)
            if isinstance(item, dict)
        ]
        assert all(not {"oneOf", "anyOf", "allOf"}.intersection(item) for item in dictionaries)


def test_task_bound_visual_tools_use_the_application_session_root(tmp_path: Path) -> None:
    document = tmp_path / "unsupported.txt"
    document.write_text("not a docx", encoding="utf-8")
    tools = {registered.name: registered for registered in build_docfit_tools(tmp_path)}

    render_result = asyncio.run(
        tools["docx_render"].handler({"input_docx": str(document), "overview": False})
    )

    assert render_result["structuredContent"]["failure"]["code"] == (
        "unsupported_document_type"
    )


def test_task_bound_tools_reject_agent_selected_root(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    tools = {registered.name: registered for registered in build_docfit_tools(task_root)}

    result = asyncio.run(
        tools["docx_inspect"].handler(
            {"task_root": str(outside), "input_docx": "outside.docx"}
        )
    )

    assert result["structuredContent"]["failure"]["code"] == "task_root_mismatch"


def test_real_docx_tools_expose_versioned_v2_schemas_without_backend_selector() -> None:
    result = asyncio.run(docx_inspect.handler({}))

    assert result["structuredContent"]["status"] == "needs_input"
    assert result["structuredContent"]["failure"]["origin"] == "request"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    for registered in (docx_inspect, docx_edit, docx_render, docx_validate):
        assert registered.input_schema.get("additionalProperties") is False
    render_properties = docx_render.input_schema["properties"]
    assert set(render_properties) == {"input_docx", "overview"}
    assert not {"provider", "backend", "engine"}.intersection(render_properties)
    edit_actions = docx_edit.input_schema["properties"]["operations"]["items"]["properties"][
        "action"
    ]["enum"]
    assert "import_content_objects" in edit_actions
    assert "import_template_sections" in edit_actions
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
        docx_visual_review.handler(
            {"render_ref": render_ref, "mode": "pages", "pages": [1]}
        )
    )
    image_content = next(item for item in result["content"] if item["type"] == "image")

    assert image_content["mimeType"] == "image/png"
    assert base64.b64decode(image_content["data"]).startswith(b"\x89PNG\r\n\x1a\n")
