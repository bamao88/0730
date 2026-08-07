from __future__ import annotations

from docfit.tools.template_tools import (
    TEMPLATE_FULL_TOOL_NAMES,
    TEMPLATE_LOGICAL_TOOL_NAMES,
    TEMPLATE_TOOLS,
    build_template_tool_server,
)


def _nested(value: object) -> list[object]:
    if isinstance(value, dict):
        return [value, *(child for item in value.values() for child in _nested(item))]
    if isinstance(value, list):
        return [child for item in value for child in _nested(item)]
    return []


def test_candidate_template_server_has_four_domain_and_two_visual_tools() -> None:
    assert TEMPLATE_LOGICAL_TOOL_NAMES == (
        "template_observe",
        "template_mutate",
        "template_compare",
        "template_build",
    )
    assert (
        *(f"mcp__docfit__{name}" for name in TEMPLATE_LOGICAL_TOOL_NAMES),
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
    ) == TEMPLATE_FULL_TOOL_NAMES
    assert tuple(tool.name for tool in TEMPLATE_TOOLS) == TEMPLATE_LOGICAL_TOOL_NAMES
    assert build_template_tool_server()["name"] == "docfit"


def test_candidate_tool_annotations_and_schemas_are_conservative() -> None:
    by_name = {tool.name: tool for tool in TEMPLATE_TOOLS}
    for name in ("template_observe", "template_compare"):
        annotations = by_name[name].annotations
        assert annotations is not None
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is False
        assert annotations.idempotentHint is True
        assert annotations.openWorldHint is True
    for name in ("template_mutate", "template_build"):
        annotations = by_name[name].annotations
        assert annotations is not None
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is False
        assert annotations.idempotentHint is False
        assert annotations.openWorldHint is False
    for registered in TEMPLATE_TOOLS:
        assert registered.input_schema.get("additionalProperties") is False
        dictionaries = [item for item in _nested(registered.input_schema) if isinstance(item, dict)]
        assert all(not {"oneOf", "anyOf", "allOf"}.intersection(item) for item in dictionaries)
