from __future__ import annotations

import asyncio
import base64

from docfit.tools import (
    DOCFIT_TOOLS,
    FULL_TOOL_NAMES,
    LOGICAL_TOOL_NAMES,
    build_docfit_server,
    docx_inspect,
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
    assert build_docfit_server()["name"] == "docfit"


def test_real_docx_tools_are_explicit_m0_boundaries() -> None:
    result = asyncio.run(docx_inspect.handler({}))

    assert result["is_error"] is True
    assert "m0_not_implemented" in result["content"][0]["text"]


def test_visual_review_returns_a_real_image_without_leaking_marker_in_text() -> None:
    result = asyncio.run(docx_visual_review.handler({"mode": "m0_image_smoke"}))
    text_content = [item["text"] for item in result["content"] if item["type"] == "text"]
    image_content = next(item for item in result["content"] if item["type"] == "image")

    assert all(SMOKE_MARKER not in text for text in text_content)
    assert image_content["mimeType"] == "image/png"
    assert base64.b64decode(image_content["data"]).startswith(b"\x89PNG\r\n\x1a\n")
