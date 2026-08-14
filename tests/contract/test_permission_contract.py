from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from docfit.app.agent import (
    AGENT_SDK_MAX_BUFFER_BYTES,
    AUTO_APPROVED_TOOL_NAMES,
    BUILTIN_TOOLS,
    DIRECTORY_POLICY,
    FORBIDDEN_TOOLS,
    LOGGING_POLICY,
    MAIN_AGENT_READ_POLICY,
    READ_ONLY_BUILTIN_TOOLS,
    READ_ONLY_SUBAGENT_TOOLS,
    SKILL_NAMES,
    SUBAGENT_NAME,
    TRUSTED_BASIC_TOOLS,
    PermissionAuditEvent,
    ReadPathPolicy,
    build_agent_options,
    build_read_path_policy,
    build_unit_analyst_definition,
    make_agent_gate_hook,
    make_permission_callback,
    make_read_path_gate_hook,
)
from docfit.tools import FULL_TOOL_NAMES


def test_options_expose_trusted_main_tools_and_one_five_tool_server(tmp_path: Path) -> None:
    options = build_agent_options(
        cwd=tmp_path,
        agent_env={"ANTHROPIC_BASE_URL": "https://example.invalid/"},
        model="test-model",
    )

    assert tuple(options.tools or ()) == BUILTIN_TOOLS
    assert tuple(options.allowed_tools) == AUTO_APPROVED_TOOL_NAMES
    assert set(options.disallowed_tools) == set(FORBIDDEN_TOOLS)
    assert isinstance(options.mcp_servers, dict)
    assert tuple(options.mcp_servers) == ("docfit",)
    assert options.strict_mcp_config is True
    assert options.permission_mode == "default"
    assert options.setting_sources == ["project"]
    assert options.skills == list(SKILL_NAMES)
    assert options.agents is not None
    assert tuple(options.agents) == (SUBAGENT_NAME,)
    assert options.agents[SUBAGENT_NAME] == build_unit_analyst_definition()
    assert options.hooks is not None
    assert tuple(options.hooks) == ("PreToolUse",)
    assert len(options.hooks["PreToolUse"]) == 2
    assert options.hooks["PreToolUse"][0].matcher == "Read|Glob|Grep"
    assert options.hooks["PreToolUse"][1].matcher == "Agent"
    assert options.env == {"ANTHROPIC_BASE_URL": "https://example.invalid/"}
    assert options.model == "test-model"
    assert options.max_buffer_size == AGENT_SDK_MAX_BUFFER_BYTES
    assert options.max_buffer_size >= 16 * 1024 * 1024
    assert DIRECTORY_POLICY == (
        "input_read_only",
        "work_writable",
        "output_writable",
        "outside_task_denied",
    )
    assert LOGGING_POLICY == "metadata_only_no_document_body"
    assert MAIN_AGENT_READ_POLICY == (
        "project_skill_references_read_only",
        "product_knowledge_package_read_only",
        "current_task_input_read_only",
        "current_task_work_read_only",
        "current_task_output_read_only",
        "realpath_before_authorization",
        "sensitive_outside_and_symlink_escape_denied",
    )
    assert set(READ_ONLY_BUILTIN_TOOLS).isdisjoint(FORBIDDEN_TOOLS)
    assert TRUSTED_BASIC_TOOLS == ("Bash", "Write")
    assert set(TRUSTED_BASIC_TOOLS).isdisjoint(FORBIDDEN_TOOLS)
    assert set(TRUSTED_BASIC_TOOLS) <= set(options.allowed_tools)


def test_observation_hook_adds_lifecycle_sources_without_replacing_agent_gate(
    tmp_path: Path,
) -> None:
    async def observe(*_: object) -> dict[str, object]:
        return {}

    options = build_agent_options(cwd=tmp_path, observation_hook=observe)  # type: ignore[arg-type]

    assert options.hooks is not None
    assert set(options.hooks) == {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SubagentStart",
        "SubagentStop",
    }
    assert len(options.hooks["PreToolUse"]) == 3
    assert options.hooks["PreToolUse"][0].matcher is None
    assert options.hooks["PreToolUse"][1].matcher == "Read|Glob|Grep"
    assert options.hooks["PreToolUse"][2].matcher == "Agent"


def test_registered_and_trusted_tools_are_approved_if_callback_is_consulted() -> None:
    async def ask_user(_: str) -> str:
        raise AssertionError("Pre-approved Tool approval must not ask the CLI")

    callback = make_permission_callback(ask_user)
    context = ToolPermissionContext()

    for tool_name in ("Skill", *FULL_TOOL_NAMES, *TRUSTED_BASIC_TOOLS):
        result = asyncio.run(callback(tool_name, {}, context))
        assert isinstance(result, PermissionResultAllow)


def _read_policy_fixture(tmp_path: Path) -> tuple[ReadPathPolicy, dict[str, Path]]:
    project = tmp_path / "project"
    skill_reference = (
        project / ".claude" / "skills" / "convert-thesis" / "references" / "safe.md"
    )
    knowledge_reference = (
        project
        / "src"
        / "docfit"
        / "knowledge"
        / "package"
        / "v1"
        / "knowledge.md"
    )
    task_root = tmp_path / "task"
    task_input = task_root / "input" / "evidence.txt"
    task_work = task_root / "work" / "analysis.md"
    task_output = task_root / "result.json"
    other_task = tmp_path / "other-task" / "secret.txt"
    credential = task_root / "input" / "agent.env"
    git_file = project / ".git" / "config"
    for path in (
        skill_reference,
        knowledge_reference,
        task_input,
        task_work,
        task_output,
        other_task,
        credential,
        git_file,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name, encoding="utf-8")
    policy = build_read_path_policy(project=project, cwd=project, task_root=task_root)
    return policy, {
        "project": project,
        "skill": skill_reference,
        "knowledge": knowledge_reference,
        "input": task_input,
        "work": task_work,
        "output": task_output,
        "task_root": task_root,
        "other_task": other_task,
        "credential": credential,
        "git": git_file,
    }


def test_read_glob_and_grep_are_allowed_only_under_canonical_roots(tmp_path: Path) -> None:
    policy, paths = _read_policy_fixture(tmp_path)

    for path in (
        paths["skill"],
        paths["knowledge"],
        paths["input"],
        paths["work"],
        paths["output"],
    ):
        decision = policy.authorize("Read", {"file_path": str(path)})
        assert decision.allowed is True
        assert decision.updated_input == {"file_path": str(path.resolve())}

    glob_decision = policy.authorize(
        "Glob",
        {"path": str(paths["work"].parent), "pattern": "**/*.md"},
    )
    grep_decision = policy.authorize(
        "Grep",
        {"path": str(paths["task_root"]), "pattern": "evidence"},
    )
    assert glob_decision.allowed is True
    assert grep_decision.allowed is False
    assert grep_decision.reason_code == "read_sensitive_path_denied"

    paths["credential"].unlink()
    grep_decision = policy.authorize(
        "Grep",
        {"path": str(paths["task_root"]), "pattern": "evidence"},
    )
    assert grep_decision.allowed is True
    assert grep_decision.updated_input == {
        "path": str(paths["task_root"].resolve()),
        "pattern": "evidence",
    }


def test_read_policy_denies_sensitive_outside_other_task_and_symlink_escape(
    tmp_path: Path,
) -> None:
    policy, paths = _read_policy_fixture(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    symlink = paths["task_root"] / "work" / "escape.md"
    symlink.symlink_to(outside)

    denied_inputs = (
        ("Read", {"file_path": str(paths["credential"])}),
        ("Read", {"file_path": str(paths["git"])}),
        ("Read", {"file_path": str(paths["other_task"])}),
        ("Read", {"file_path": str(symlink)}),
        ("Read", {"file_path": str(tmp_path / "missing.txt")}),
        ("Glob", {"pattern": "**/*.md"}),
        ("Glob", {"path": str(paths["task_root"]), "pattern": "../**/*"}),
        (
            "Grep",
            {
                "path": str(paths["task_root"]),
                "pattern": "anything",
                "glob": "../*.md",
            },
        ),
    )
    for tool_name, tool_input in denied_inputs:
        decision = policy.authorize(tool_name, tool_input)
        assert decision.allowed is False

    paths["credential"].unlink()
    search_escape = policy.authorize(
        "Grep",
        {"path": str(paths["task_root"]), "pattern": "anything"},
    )
    assert search_escape.allowed is False
    assert search_escape.reason_code == "read_search_symlink_denied"


def test_project_skill_root_cannot_be_replaced_by_an_escaping_symlink(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    outside_skills = tmp_path / "outside-skills"
    outside_reference = outside_skills / "convert-thesis" / "references" / "unsafe.md"
    outside_reference.parent.mkdir(parents=True)
    outside_reference.write_text("outside", encoding="utf-8")
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "skills").symlink_to(outside_skills, target_is_directory=True)

    policy = build_read_path_policy(project=project, cwd=project)
    decision = policy.authorize("Read", {"file_path": str(outside_reference)})

    assert decision.allowed is False
    assert decision.reason_code == "read_path_outside_allowed_roots"


def test_read_path_hook_canonicalizes_allowed_input_and_denies_escape(tmp_path: Path) -> None:
    policy, paths = _read_policy_fixture(tmp_path)
    events: list[PermissionAuditEvent] = []
    hook = make_read_path_gate_hook(policy, events.append)
    context = {"signal": None}

    allowed = asyncio.run(
        hook(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "session",
                "transcript_path": "/tmp/transcript",
                "cwd": str(paths["project"]),
                "tool_name": "Read",
                "tool_input": {"file_path": str(paths["skill"])},
                "tool_use_id": "allowed-read",
            },
            "allowed-read",
            context,
        )
    )
    denied = asyncio.run(
        hook(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "session",
                "transcript_path": "/tmp/transcript",
                "cwd": str(paths["project"]),
                "tool_name": "Read",
                "tool_input": {"file_path": str(paths["other_task"])},
                "tool_use_id": "denied-read",
            },
            "denied-read",
            context,
        )
    )

    assert allowed["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert allowed["hookSpecificOutput"]["updatedInput"] == {
        "file_path": str(paths["skill"].resolve())
    }
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert [(event.tool_name, event.decision) for event in events] == [
        ("Read", "allow"),
        ("Read", "deny"),
    ]


def test_permission_callback_enforces_the_same_read_path_policy(tmp_path: Path) -> None:
    policy, paths = _read_policy_fixture(tmp_path)

    async def ask_user(_: str) -> str:
        raise AssertionError("Read permission must not ask the CLI")

    callback = make_permission_callback(ask_user, read_path_policy=policy)
    allowed = asyncio.run(
        callback(
            "Read",
            {"file_path": str(paths["input"])},
            ToolPermissionContext(),
        )
    )
    denied = asyncio.run(
        callback(
            "Read",
            {"file_path": str(paths["other_task"])},
            ToolPermissionContext(),
        )
    )

    assert isinstance(allowed, PermissionResultAllow)
    assert allowed.updated_input == {"file_path": str(paths["input"].resolve())}
    assert isinstance(denied, PermissionResultDeny)
    assert "authorized path policy" in denied.message


def test_only_named_read_only_subagent_is_approved() -> None:
    async def ask_user(_: str) -> str:
        raise AssertionError("Agent approval must not ask the CLI")

    events: list[PermissionAuditEvent] = []
    callback = make_permission_callback(ask_user, audit=events.append)
    context = ToolPermissionContext()

    allowed = asyncio.run(
        callback("Agent", {"subagent_type": SUBAGENT_NAME, "prompt": "bounded"}, context)
    )
    assert isinstance(allowed, PermissionResultAllow)

    for subagent_type in ("general-purpose", "unknown-agent", None):
        denied = asyncio.run(
            callback("Agent", {"subagent_type": subagent_type}, context)
        )
        assert isinstance(denied, PermissionResultDeny)
        assert SUBAGENT_NAME in denied.message

    assert [
        (event.tool_name, event.decision, event.subagent_type) for event in events
    ] == [
        ("Agent", "allow", SUBAGENT_NAME),
        ("Agent", "deny", "general-purpose"),
        ("Agent", "deny", "unknown-agent"),
        ("Agent", "deny", None),
    ]


def test_unit_analyst_definition_has_only_two_read_only_tools() -> None:
    definition = build_unit_analyst_definition()

    assert tuple(definition.tools or ()) == READ_ONLY_SUBAGENT_TOOLS
    assert definition.skills == []
    assert definition.memory is None
    assert definition.mcpServers == ["docfit"]
    assert definition.permissionMode == "dontAsk"
    assert set(definition.disallowedTools or ()) >= {
        "Bash",
        "Write",
        "Read",
        "Glob",
        "Grep",
        "Agent",
        "Skill",
        "AskUserQuestion",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_validate",
    }


def test_agent_pre_tool_hook_allows_only_named_subagent() -> None:
    events: list[PermissionAuditEvent] = []
    hook = make_agent_gate_hook(events.append)
    context = {"signal": None}

    allowed = asyncio.run(
        hook(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "session",
                "transcript_path": "/tmp/transcript",
                "cwd": "/tmp",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": SUBAGENT_NAME},
                "tool_use_id": "allowed",
            },
            "allowed",
            context,
        )
    )
    assert allowed["hookSpecificOutput"]["permissionDecision"] == "allow"

    for subagent_type in ("general-purpose", "unknown-agent", None):
        denied = asyncio.run(
            hook(
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session",
                    "transcript_path": "/tmp/transcript",
                    "cwd": "/tmp",
                    "tool_name": "Agent",
                    "tool_input": {"subagent_type": subagent_type},
                    "tool_use_id": "denied",
                },
                "denied",
                context,
            )
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    assert [
        (event.tool_name, event.decision, event.subagent_type) for event in events
    ] == [
        ("Agent", "allow", SUBAGENT_NAME),
        ("Agent", "deny", "general-purpose"),
        ("Agent", "deny", "unknown-agent"),
        ("Agent", "deny", None),
    ]


def test_ask_user_question_is_forwarded_to_cli_input() -> None:
    prompts: list[str] = []

    async def ask_user(prompt: str) -> str:
        prompts.append(prompt)
        return "continue-m0"

    callback = make_permission_callback(ask_user)
    tool_input = {
        "questions": [
            {
                "header": "M0",
                "question": "Continue token?",
                "options": [{"label": "Yes", "description": "Continue the same session."}],
            }
        ]
    }

    result = asyncio.run(callback("AskUserQuestion", tool_input, ToolPermissionContext()))

    assert isinstance(result, PermissionResultAllow)
    assert result.updated_input == {
        **tool_input,
        "answers": {"Continue token?": "continue-m0"},
    }
    assert prompts and "Continue token?" in prompts[0]


def test_unmatched_tools_are_denied() -> None:
    async def ask_user(_: str) -> str:
        return "unused"

    callback = make_permission_callback(ask_user)

    for tool_name in (
        "Edit",
        "Web",
        "WebSearch",
        "WebFetch",
        "mcp__docfit__unknown",
    ):
        result = asyncio.run(callback(tool_name, {}, ToolPermissionContext()))
        assert isinstance(result, PermissionResultDeny)
        assert "denies unmatched tool" in result.message
