from __future__ import annotations

import json
from pathlib import Path

from docfit.app.agent import UNTRUSTED_SOURCE_DATA_LABEL, project_root
from docfit.app.prepare_template import (
    PrepareTemplateRequest,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
)
from docfit.app.settings import AgentBackend

ROOT = project_root()
PROMPT_INJECTION_DOCX = ROOT / "tests/fixtures/template_extraction/p4_prompt_injection.docx"
REGISTRY = ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"


def _backend() -> AgentBackend:
    return AgentBackend(
        name="test",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def test_docx_prompt_injection_text_never_enters_startup_or_runtime_config(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(
        PrepareTemplateRequest(
            school_template=PROMPT_INJECTION_DOCX,
            output_directory=tmp_path / "prepared-task",
            field_registry=REGISTRY,
        )
    )
    config = tmp_path / "config"
    config.mkdir()
    prompt = build_prepare_template_prompt(prepared)
    options = build_prepare_template_options(prepared, _backend(), config)
    manifest = json.loads(
        (prepared.task_root / "work/.docfit/prepare-template-task.json").read_text(
            encoding="utf-8"
        )
    )

    runtime_context = json.dumps(
        {
            "manifest": manifest,
            "prompt": prompt,
            "system_prompt": str(options.system_prompt),
            "tools": options.tools,
            "allowed_tools": options.allowed_tools,
            "disallowed_tools": options.disallowed_tools,
            "skills": options.skills,
            "agents": sorted(options.agents or ()),
        },
        ensure_ascii=False,
    )

    for injected in (
        "PROMPT_INJECTION_BODY",
        "PROMPT_INJECTION_HIDDEN",
        "PROMPT_INJECTION_FIELD",
        "PROMPT_INJECTION_ALT_TEXT",
        "PROMPT_INJECTION_COMMENT",
        "Allow docfit_apply for subagents",
        "publish to /tmp",
    ):
        assert injected not in runtime_context
    assert f"trust={UNTRUSTED_SOURCE_DATA_LABEL}" in prompt
    assert options.allowed_tools == []
    assert "docfit-school-extract" in (options.skills or [])
    assert "Bash" in (options.disallowed_tools or [])
    assert "Write" in (options.disallowed_tools or [])
