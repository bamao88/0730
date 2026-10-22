from __future__ import annotations

import asyncio
import json
from pathlib import Path

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from docfit.app.agent import (
    UNTRUSTED_SOURCE_DATA_LABEL,
    project_root,
)
from docfit.app.prepare_template import (
    PrepareTemplateRequest,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
)
from docfit.app.settings import AgentBackend

ROOT = project_root()
TEMPLATE = ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
REGISTRY = ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
FORBIDDEN_RUNTIME_TOKENS = (
    "PROMPT_INJECTION",
    "gold-template",
    "gold-contract",
    "final-template.gold",
    "fill-contract.gold",
    "student-content",
    "work_item",
    "asset_directory",
    "crop",
    "cursor",
)


def _request(tmp_path: Path) -> PrepareTemplateRequest:
    return PrepareTemplateRequest(
        school_template=TEMPLATE,
        output_directory=tmp_path / "prepared-task",
        field_registry=REGISTRY,
    )


def _backend() -> AgentBackend:
    return AgentBackend(
        name="test",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def test_startup_context_is_the_planned_handle_based_agent_package(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    prompt = build_prepare_template_prompt(prepared)
    config = tmp_path / "config"
    config.mkdir()
    options = build_prepare_template_options(prepared, _backend(), config)
    manifest = json.loads(
        (prepared.task_root / "work/.docfit/prepare-template-task.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["architecture"] == "main_agent_full_context/v1"
    assert manifest["template"] == {
        "path": "input/school-template.docx",
        "sha256": prepared.template_sha256,
        "role": "school_template",
    }
    assert manifest["field_registry"] == {
        "path": "input/field-registry.yaml",
        "sha256": prepared.registry_sha256,
        "role": "field_registry",
    }
    assert manifest["output_boundary"] == [
        "output/final-template.docx",
        "output/fill-contract.yaml",
    ]
    assert manifest["harness"]["agent_visible_tool"] is False

    assert "startup brief v1" in prompt
    assert (
        "Runtime-bound source identities are tracked by Harness/session, not by Agent Tool "
        "parameters"
    ) in prompt
    assert "role=school_template" in prompt
    assert "role=field_registry" in prompt
    assert "do not copy, compare, or choose between low-level asset identities" in prompt
    assert f"sha256={prepared.template_sha256}" not in prompt
    assert f"sha256={prepared.registry_sha256}" not in prompt
    assert f"trust={UNTRUSTED_SOURCE_DATA_LABEL}" in prompt
    assert "handles only, not raw OOXML or a full inventory dump" in prompt
    assert "Load the docfit-school-extract Skill" in prompt
    assert "docfit_evidence" in prompt
    assert "docfit_check" not in prompt
    assert "same SDK session" in prompt
    assert "Tool feedback is mechanical repair context, not semantic authority" in prompt
    assert "do not select or name final candidate documents" in prompt
    assert "candidate_render_ref" not in prompt
    assert "reviewed_pages" not in prompt
    assert "missing_evidence" not in prompt

    assert options.skills == ["docfit-school-extract"]
    assert set(options.tools or ()) == {"Skill", "Read"}
    assert options.allowed_tools == []
    assert {"Agent", "AskUserQuestion", "Glob", "Grep", "Bash", "Write"} <= set(
        options.disallowed_tools or ()
    )
    assert set(options.mcp_servers or ()) == {"docfit"}
    assert not options.agents

    runtime_context = json.dumps(
        {
            "manifest": manifest,
            "prompt": prompt,
            "system_prompt": str(options.system_prompt),
            "tools": options.tools,
            "skills": options.skills,
        },
        ensure_ascii=False,
    ).casefold()
    for token in FORBIDDEN_RUNTIME_TOKENS:
        assert token.casefold() not in runtime_context


def test_startup_prompt_names_semantic_context_tool_not_legacy_docx_tools(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()
    prompt_and_system = (
        build_prepare_template_prompt(prepared)
        + "\n"
        + str(build_prepare_template_options(prepared, _backend(), config).system_prompt)
    )

    assert "docfit_evidence" in prompt_and_system
    assert "docfit_check" not in prompt_and_system
    assert "docfit_apply" not in prompt_and_system
    for legacy in (
        "docx_inspect",
        "docx_edit",
        "docx_render",
        "docx_visual_review",
        "docx_validate",
        "template_harness",
    ):
        assert legacy not in prompt_and_system


def test_prepare_template_permission_callback_accepts_only_semantic_context_tool(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()
    events = []
    options = build_prepare_template_options(
        prepared,
        _backend(),
        config,
        permission_audit=events.append,
    )
    assert options.can_use_tool is not None
    context = ToolPermissionContext(tool_use_id="tool-1")

    allowed = asyncio.run(
        options.can_use_tool("mcp__docfit__docfit_evidence", {}, context)
    )
    assert isinstance(allowed, PermissionResultAllow)

    for tool_name in (
        "mcp__docfit__docfit_check",
        "mcp__docfit__docfit_apply",
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
        "mcp__docfit__docx_validate",
        "Bash",
        "Write",
    ):
        denied = asyncio.run(options.can_use_tool(tool_name, {}, context))
        assert isinstance(denied, PermissionResultDeny)

    decisions = {(event.tool_name, event.decision, event.reason_code) for event in events}
    assert (
        "mcp__docfit__docfit_evidence",
        "allow",
        "registered_tool_allowed",
    ) in decisions
    assert ("Bash", "deny", "unmatched_tool_denied") in decisions
