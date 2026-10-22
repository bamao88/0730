from __future__ import annotations

import ast
import json
from pathlib import Path

from docfit.fields import FieldRegistrySnapshot
from docfit.tools import DOCFIT_EVIDENCE_TOOL, build_docfit_tools

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def test_template_runtime_profile_does_not_expose_docx_edit_mechanics(
    tmp_path: Path,
) -> None:
    tools = build_docfit_tools(
        tmp_path,
        include_docx_tools=False,
        template_semantic_only=True,
    )

    assert [tool.name for tool in tools] == [DOCFIT_EVIDENCE_TOOL]
    schema_text = json.dumps(tools[0].input_schema, ensure_ascii=False)
    for retired_runtime_field in (
        "field_registry",
        "field_id",
        "slot_ref",
        "members",
        "toc_entries",
        "target_ref",
        "object_ref",
    ):
        assert retired_runtime_field not in schema_text


def test_template_runtime_profile_does_not_expose_check_apply_or_raw_docx_tools(
    tmp_path: Path,
) -> None:
    tools = build_docfit_tools(
        tmp_path,
        include_docx_tools=False,
        template_semantic_only=True,
    )

    assert {
        "docfit_check",
        "docfit_apply",
        "docx_inspect",
        "docx_edit",
        "docx_render",
        "docx_visual_review",
        "docx_validate",
    }.isdisjoint({tool.name for tool in tools})


def test_prepare_template_call_paths_always_select_the_semantic_only_tool_profile() -> None:
    source = (_PROJECT_ROOT / "src/docfit/app/prepare_template.py").read_text(
        encoding="utf-8"
    )
    calls = _calls_named(ast.parse(source), "build_docfit_server")

    assert len(calls) == 2
    for call in calls:
        keywords = {item.arg: item.value for item in call.keywords if item.arg is not None}
        assert isinstance(keywords.get("include_docx_tools"), ast.Constant)
        assert keywords["include_docx_tools"].value is False
        assert isinstance(keywords.get("template_semantic_only"), ast.Constant)
        assert keywords["template_semantic_only"].value is True


def test_runtime_source_scan_has_no_registry_semantic_search_call_path() -> None:
    runtime_roots = (
        _PROJECT_ROOT / "src/docfit/app",
        _PROJECT_ROOT / "src/docfit/tools",
        _PROJECT_ROOT / "src/docfit/template",
    )
    non_regex_search_calls: list[str] = []
    for root in runtime_roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "search"
                ):
                    continue
                receiver = ast.unparse(node.func.value)
                if receiver == "re" or receiver.endswith("_RE"):
                    continue
                non_regex_search_calls.append(
                    f"{path.relative_to(_PROJECT_ROOT)}:{node.lineno}:{receiver}.search"
                )

    assert not hasattr(FieldRegistrySnapshot, "search")
    assert non_regex_search_calls == []
