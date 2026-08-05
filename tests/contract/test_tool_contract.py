from __future__ import annotations

import asyncio
import base64
import json

from docfit.tools import (
    AGENT_TOOL_RESULT_MAX_CHARS,
    DOCFIT_TOOLS,
    FULL_TOOL_NAMES,
    LOGICAL_TOOL_NAMES,
    build_docfit_server,
    docx_edit,
    docx_inspect,
    docx_render,
    docx_validate,
    docx_visual_review,
)
from docfit.tools.image_smoke import SMOKE_MARKER


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


def test_real_docx_tools_expose_versioned_m1_schemas_without_backend_selector() -> None:
    result = asyncio.run(docx_inspect.handler({}))

    assert result["structuredContent"]["status"] == "needs_input"
    assert result["structuredContent"]["failure"]["origin"] == "request"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    for registered in (docx_inspect, docx_edit, docx_render, docx_validate):
        assert registered.input_schema.get("additionalProperties") is False
    render_properties = docx_render.input_schema["properties"]
    assert set(render_properties) >= {
        "input_docx",
        "render_intent",
        "output_dir",
        "baseline_render_ref",
    }
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


def test_visual_review_returns_a_real_image_without_leaking_marker_in_text() -> None:
    assert "oneOf" not in docx_visual_review.input_schema
    assert docx_visual_review.input_schema["required"] == ["mode"]
    assert "m0_image_smoke" in docx_visual_review.input_schema["properties"]["mode"]["enum"]

    result = asyncio.run(docx_visual_review.handler({"mode": "m0_image_smoke"}))
    text_content = [item["text"] for item in result["content"] if item["type"] == "text"]
    image_content = next(item for item in result["content"] if item["type"] == "image")

    assert all(SMOKE_MARKER not in text for text in text_content)
    assert image_content["mimeType"] == "image/png"
    assert base64.b64decode(image_content["data"]).startswith(b"\x89PNG\r\n\x1a\n")
