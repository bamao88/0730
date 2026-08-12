from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk.types import ResultMessage

from docfit.app.cli import build_parser
from docfit.app.prepare_template import (
    PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS,
    PREPARE_TEMPLATE_MAX_SEMANTIC_ATTEMPTS,
    PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT,
    PREPARE_TEMPLATE_VISUAL_TURN_LIMIT,
    VISUAL_REVIEW_OUTPUT_SCHEMA,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _append_agent_live_event,
    _ExecutionMetrics,
    _review_final_document,
    _run_sdk_session,
    _run_semantic_work_item,
    _validated_visual_pages,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
    run_prepare_template,
    run_template_agent,
)
from docfit.app.settings import AgentBackend
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.template_tools import (
    ReviewBatchState,
    SemanticWorkItemState,
    _agent_payload,
    _bounded_work_item_payload,
    _mechanical_blank_segments,
    _translate_operation,
    _validated_decision_operations,
    _validated_work_item_operations,
    build_template_review_tool_server,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = PROJECT_ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
COUNTS = {"slot": 0, "remove": 0, "manual": 0, "gap": 0, "unresolved": 0}


def _request(tmp_path: Path) -> PrepareTemplateRequest:
    return PrepareTemplateRequest(
        school_template=TEMPLATE,
        output_directory=tmp_path / "prepared-task",
    )


def _backend() -> AgentBackend:
    return AgentBackend(
        name="minimax",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def test_prepare_task_copies_only_inputs_skill_and_empty_output(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    assert prepared.template_path.stat().st_mode & 0o222 == 0
    assert prepared.registry_source == REGISTRY.resolve()
    assert prepared.template_sha256 == sha256_file(TEMPLATE)
    skill = prepared.task_root / ".claude/skills/docfit-school-extract"
    references = sorted(item.name for item in (skill / "references").iterdir())
    assert references == [
        "body-structure.md",
        "collection-and-optional-sections.md",
        "effective-style.md",
        "final-visual-review.md",
        "generated-content.md",
        "logical-page-starts.md",
        "object-safety.md",
    ]
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for reference in references:
        assert f"](references/{reference})" in skill_text
    assert "应用负责选择当前工作项、推进流程、限制重试" in skill_text
    assert "此时禁止主动逐页巡检" in skill_text
    assert "只有收到应用绑定的最终全页 PNG 批次时" in skill_text
    assert "cursor" not in skill_text.casefold()
    assert "document_ref" not in skill_text
    assert "template_publish" not in skill_text
    assert not any((prepared.task_root / "output").iterdir())


def test_prepare_task_resumes_matching_unpublished_checkpoint(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    progress = prepared.task_root / "work/.docfit/template-workspace-v1/task-progress.json"
    progress.parent.mkdir(parents=True)
    progress.write_text('{"region_index": 15}', encoding="utf-8")

    assert prepare_template_task(request) == prepared
    assert progress.read_text(encoding="utf-8") == '{"region_index": 15}'


def test_prepare_task_rejects_symlinked_completed_output(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    (prepared.task_root / "output/final-template.docx").symlink_to(TEMPLATE)

    with pytest.raises(ToolFailure) as caught:
        prepare_template_task(request)

    assert caught.value.code == "prepare_checkpoint_invalid"


def test_prepare_task_rejects_resume_with_different_source(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepare_template_task(request)
    different = tmp_path / "different.docx"
    different.write_bytes(TEMPLATE.read_bytes() + b"different")

    with pytest.raises(ToolFailure) as caught:
        prepare_template_task(
            PrepareTemplateRequest(
                school_template=different,
                output_directory=request.output_directory,
            )
        )

    assert caught.value.code == "prepare_source_mismatch"


@pytest.mark.parametrize(
    ("role", "turn_limit"),
    [
        ("semantic", PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT),
        ("visual", PREPARE_TEMPLATE_VISUAL_TURN_LIMIT),
    ],
)
def test_options_are_role_scoped_and_application_owned(
    tmp_path: Path,
    role: str,
    turn_limit: int,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()
    server = build_template_review_tool_server(
        ReviewBatchState(payload={"batch_pages": [1]}, images=[])
    )

    options = build_prepare_template_options(
        prepared,
        _backend(),
        config,
        role=role,  # type: ignore[arg-type]
        mcp_server=server,
    )

    assert options.max_turns == turn_limit
    assert options.tools == ["Skill", "Read"]
    assert {"AskUserQuestion", "Bash", "Write", "Agent", "Glob", "Grep"} <= set(
        options.disallowed_tools or ()
    )
    assert options.mcp_servers is not None
    assert options.output_format is not None
    output_schema = str(options.output_format)
    assert ("accepted" in output_schema) == (role == "semantic")
    assert ("defect" in output_schema) == (role == "visual")


def test_prompts_keep_semantic_and_full_page_roles_separate(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    semantic = build_prepare_template_prompt(prepared, role="semantic")
    visual = build_prepare_template_prompt(prepared, role="visual")

    assert "not only its target anchor" in semantic
    assert "batch all clear operations" in semantic
    assert "Initial Registry candidates are intentionally target-only" in semantic
    assert "An unqueried sibling never counts as having no candidate" in semantic
    assert "mechanical_blank_segments" in semantic
    assert "separate advisor-name and title blanks" in semantic
    assert "verify the candidate's meaning" in semantic
    assert "must never be reused" in semantic
    assert "preceding_landmarks" in semantic
    assert "materialize one representative content interface" in semantic
    assert "One content responsibility on one logical page gets exactly one interface" in semantic
    assert "materialize the actual sample object, never both" in semantic
    assert "第一章 文献综述" in semantic
    assert "Never turn that fixed heading into a standalone" in semantic
    assert "Reserve the repeatable body.chapters structure" in semantic
    assert "materialize a real sample body paragraph as body.paragraph" in semantic
    assert "prior locations only" in semantic
    assert "abstract page still needs its own slot" in semantic
    assert "formatting annotation is not thereby a fixed label" in semantic
    assert "do not delete a demonstrated member type" in semantic
    assert "1000-character limit" in semantic
    assert "application owns traversal" in semantic.casefold()
    assert "final review" in semantic
    assert "cursor" not in semantic.casefold()
    assert "publish" not in semantic.casefold()
    assert "every returned native full-page PNG" in visual
    assert "exactly one verdict" in visual
    assert "blank page alone is not proof" in visual
    assert "bracketed SDT labels are legitimate" in visual
    assert "do not redo template semantics" in visual.casefold()

    categories = set(
        VISUAL_REVIEW_OUTPUT_SCHEMA["properties"]["pages"]["items"]["properties"][
            "defects"
        ]["items"]["properties"]["category"]["enum"]
    )
    assert categories == {
        "clipping",
        "overlap",
        "missing_glyph",
        "table_damage",
        "spacing",
        "header_footer",
    }


def test_decision_contract_accepts_zero_operations_only_for_preserve() -> None:
    assert _validated_decision_operations("preserve", None) == []
    assert _validated_decision_operations("preserve", []) == []

    with pytest.raises(ToolFailure) as preserve_error:
        _validated_decision_operations(
            "preserve",
            [{"action": "clear_content", "object_id": "obj-" + "a" * 24}],
        )
    assert preserve_error.value.code == "preserve_operations_invalid"

    with pytest.raises(ToolFailure) as apply_error:
        _validated_decision_operations("apply", [])
    assert apply_error.value.code == "apply_operations_missing"


def test_toc_refresh_is_reserved_for_generated_content_work_item() -> None:
    operation = {
        "action": "refresh_toc",
        "object_id": "obj-" + "a" * 24,
        "entries": [
            {
                "object_id": "obj-" + "b" * 24,
                "level": 1,
            }
        ],
    }

    with pytest.raises(ToolFailure) as local_error:
        _validated_work_item_operations(
            {
                "kind": "local_region",
                "region": {"knowledge_signals": ["generated-content"]},
            },
            "apply",
            [operation],
        )
    assert local_error.value.code == "local_generated_content_read_only"

    assert _validated_work_item_operations(
        {"kind": "generated_content"},
        "apply",
        [operation],
    ) == [operation]

    with pytest.raises(ToolFailure) as mixed_error:
        _validated_work_item_operations(
            {"kind": "generated_content"},
            "apply",
            [
                operation,
                {
                    "action": "clear_content",
                    "object_id": "obj-" + "c" * 24,
                },
            ],
        )
    assert mixed_error.value.code == "generated_content_action_invalid"


@pytest.mark.parametrize(
    "operation",
    [
        {"action": "clear_content", "object_id": "obj-" + "a" * 24},
        {"action": "remove_object", "object_id": "obj-" + "a" * 24},
        {
            "action": "normalize_effective_format",
            "object_id": "obj-" + "a" * 24,
            "effective_format": {"color": "black"},
        },
    ],
)
def test_local_generated_content_rejects_every_mutation(operation: JsonObject) -> None:
    with pytest.raises(ToolFailure) as caught:
        _validated_work_item_operations(
            {
                "kind": "local_region",
                "region": {"knowledge_signals": ["generated-content"]},
            },
            "apply",
            [operation],
        )
    assert caught.value.code == "local_generated_content_read_only"


def test_initial_registry_candidates_are_limited_to_current_target() -> None:
    calls: list[str] = []

    class FakeRegistry:
        def search(self, text: str, *, limit: int) -> list[JsonObject]:
            calls.append(text)
            assert limit == 5
            return [{"field_id": "submission.date"}]

    class FakeService:
        registry = FakeRegistry()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {
                    "object_id": "obj-" + "a" * 24,
                    "text": "20 年 月 日",
                },
                "adjacent_objects": [
                    {
                        "object_id": "obj-" + "b" * 24,
                        "text": "无关的相邻对象",
                    }
                ],
            }
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )

    assert state.initial_candidates() == [
        {
            "object_id": "obj-" + "a" * 24,
            "matches": [{"field_id": "submission.date"}],
        }
    ]
    assert calls == ["20 年 月 日 20年月日"]
    assert state.offered_field_ids == {"submission.date"}


def test_agent_work_item_caps_adjacent_context_and_hides_unseen_objects() -> None:
    target_id = "obj-" + "f" * 24
    target_children = [
        {
            "object_id": f"obj-{index:024x}",
            "text": f"目标 run {index}",
            "type": "run",
            "parent_context": {"object_id": target_id},
        }
        for index in range(10)
    ]
    sibling_runs = [
        {
            "object_id": f"obj-{100 + index:024x}",
            "text": f"邻居 run {index}",
            "type": "run",
        }
        for index in range(4)
    ]
    sibling_paragraphs = [
        {
            "object_id": f"obj-{200 + index:024x}",
            "text": f"邻居段落 {index}",
            "type": "paragraph",
        }
        for index in range(14)
    ]
    adjacent = [*target_children, *sibling_runs, *sibling_paragraphs]
    internal = {
        "document_ref": "document:v1:hidden",
        "region": {
            "region_ref": "region:v1:hidden",
            "target": {"object_id": target_id, "text": "当前目标"},
            "adjacent_objects": adjacent,
        },
    }

    public = _bounded_work_item_payload(internal)

    assert "document_ref" not in public
    assert "region_ref" not in public["region"]
    assert public["region"]["adjacent_objects"] == [
        *target_children[:8],
        *sibling_paragraphs[:12],
    ]
    assert public["region"]["visible_adjacent_count"] == 20
    assert public["region"]["total_adjacent_count"] == len(adjacent)


def test_mechanical_blank_segments_keep_label_separated_values_distinct() -> None:
    parent_id = "obj-" + "f" * 24
    runs = [
        {
            "object_id": "obj-" + "1" * 24,
            "type": "run",
            "text": "指导教师:",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "2" * 24,
            "type": "run",
            "text": "                 ",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "3" * 24,
            "type": "run",
            "text": "职称",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "4" * 24,
            "type": "run",
            "text": "          ",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "5" * 24,
            "type": "run",
            "text": " ",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "6" * 24,
            "type": "run",
            "text": "    ",
            "parent_context": {"object_id": parent_id},
        },
    ]

    assert _mechanical_blank_segments(runs) == [
        {
            "parent_object_id": parent_id,
            "object_ids": ["obj-" + "2" * 24],
            "character_count": 17,
            "before_text": "指导教师:",
            "after_text": "职称",
        },
        {
            "parent_object_id": parent_id,
            "object_ids": [
                "obj-" + "4" * 24,
                "obj-" + "5" * 24,
                "obj-" + "6" * 24,
            ],
            "character_count": 15,
            "before_text": "职称",
            "after_text": None,
        },
    ]


def test_max_turn_failure_has_a_hard_attempt_bound(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    calls = 0

    class FakeService:
        registry = object()

        def workflow_progress_snapshot(self) -> JsonObject:
            return {
                "source_sha256": "a" * 64,
                "document_sha256": "a" * 64,
                "region_index": 0,
            }

        def restore_workflow_progress(self, _snapshot: JsonObject) -> None:
            return None

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        nonlocal calls
        calls += 1
        return ResultMessage(
            subtype="error_max_turns",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT,
            session_id=f"attempt-{calls}",
            terminal_reason="max_turns",
        )

    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(
            _run_semantic_work_item(
                prepared,
                _backend(),
                tmp_path,
                _ExecutionMetrics(),
                FakeService(),  # type: ignore[arg-type]
                work_item={"kind": "local_region"},
                images=[],
                internal_region_ref="internal",
                allow_preserve=True,
            )
        )

    assert caught.value.code == "semantic_work_item_attempts_exhausted"
    assert calls == PREPARE_TEMPLATE_MAX_SEMANTIC_ATTEMPTS


def test_sdk_session_times_out_when_backend_stops_emitting_events(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    exited = False

    class HangingClient:
        async def __aenter__(self) -> HangingClient:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            nonlocal exited
            exited = True

        async def query(self, _prompt: str) -> None:
            return None

        async def receive_response(self) -> Any:
            await asyncio.sleep(60)
            yield None

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_prepare_template_options",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.ClaudeSDKClient",
        lambda **_kwargs: HangingClient(),
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(TimeoutError):
        asyncio.run(
            _run_sdk_session(
                prepared,
                _backend(),
                tmp_path,
                role="semantic",
                mcp_server=object(),
                metrics=_ExecutionMetrics(),
            )
        )

    assert exited is True
    events = prepared.task_root / "work/.docfit/template-agent-live.jsonl"
    assert '"event": "session_idle_timeout"' in events.read_text(encoding="utf-8")
    assert f'"idle_timeout_seconds": {0.01}' in events.read_text(encoding="utf-8")
    assert PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS == 180


def test_application_advances_region_after_agent_accepts_one_decision(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    bound: dict[str, Any] = {}

    class FakeService:
        registry = object()

        def __init__(self) -> None:
            self.navigation: list[JsonObject] = []

        def workflow_progress_snapshot(self) -> JsonObject:
            return {
                "source_sha256": "a" * 64,
                "document_sha256": "a" * 64,
                "region_index": 0,
            }

        def restore_workflow_progress(self, _snapshot: JsonObject) -> None:
            raise AssertionError("accepted preserve must not roll back")

        def view(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
            self.navigation.append(args)
            return {"status": "ok"}, []

    service = FakeService()

    def fake_server(state: Any) -> object:
        bound["state"] = state
        return object()

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        state = bound["state"]
        state.submission = {"outcome": "preserve", "reason": "fixed school label"}
        state.post_region_ref = state.internal_region_ref
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="semantic-one",
            terminal_reason="end_turn",
            structured_output={
                "status": "accepted",
                "reason": "The fixed label remains unchanged.",
            },
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_template_semantic_tool_server",
        fake_server,
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    asyncio.run(
        _run_semantic_work_item(
            prepared,
            _backend(),
            tmp_path,
            _ExecutionMetrics(),
            service,  # type: ignore[arg-type]
            work_item={"kind": "local_region"},
            images=[],
            internal_region_ref="internal-region-ref",
            allow_preserve=True,
        )
    )

    assert service.navigation == [
        {
            "action": "next",
            "region_ref": "internal-region-ref",
            "region_outcome": "preserve",
            "reason": "fixed school label",
        }
    ]


def test_application_does_not_advance_again_when_edit_completed_navigation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    bound: dict[str, Any] = {}

    class FakeService:
        registry = object()

        def workflow_progress_snapshot(self) -> JsonObject:
            return {
                "source_sha256": "a" * 64,
                "document_sha256": "a" * 64,
                "region_index": 39,
            }

        def restore_workflow_progress(self, _snapshot: JsonObject) -> None:
            raise AssertionError("accepted final edit must not roll back")

        def view(self, _args: JsonObject) -> tuple[JsonObject, list[Path]]:
            raise AssertionError("the edit response already completed navigation")

    def fake_server(state: Any) -> object:
        bound["state"] = state
        return object()

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        state = bound["state"]
        state.submission = {
            "outcome": "handled",
            "reason": "removed final instruction shape",
        }
        state.mutated = True
        state.post_region_ref = None
        state.navigation_done = True
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="semantic-final",
            terminal_reason="end_turn",
            structured_output={
                "status": "accepted",
                "reason": "The final edit completed the semantic traversal.",
            },
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_template_semantic_tool_server",
        fake_server,
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    asyncio.run(
        _run_semantic_work_item(
            prepared,
            _backend(),
            tmp_path,
            _ExecutionMetrics(),
            FakeService(),  # type: ignore[arg-type]
            work_item={"kind": "local_region"},
            images=[],
            internal_region_ref="stale-pre-edit-region-ref",
            allow_preserve=True,
        )
    )


def test_application_owns_visual_cursor_and_agent_sees_only_bound_pages(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    bound: dict[str, Any] = {}

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[JsonObject] = []
            self.receipts: list[JsonObject] = []

        def current_document_ref(self) -> str:
            return "internal-document-ref"

        def final_review(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
            self.calls.append(args)
            page = len(self.calls)
            return (
                {
                    "document_ref": "internal-document-ref",
                    "render_ref": "internal-render-ref",
                    "page_count": 2,
                    "batch_pages": [page],
                    "next_cursor": "internal-page-two" if page == 1 else None,
                },
                [],
            )

        def record_final_review_verdict(self, **kwargs: Any) -> JsonObject:
            self.receipts.append(kwargs)
            return {"status": "clean"}

    service = FakeService()

    def fake_server(state: Any) -> object:
        bound["state"] = state
        return object()

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        payload = _agent_payload(bound["state"].payload)
        assert "next_cursor" not in payload
        assert "document_ref" not in payload
        page = payload["batch_pages"][0]
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id=f"visual-{page}",
            terminal_reason="end_turn",
            structured_output={
                "pages": [{"page": page, "verdict": "clean", "defects": []}],
                "summary": "No visible rendering defect.",
            },
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_template_review_tool_server",
        fake_server,
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    defects = asyncio.run(
        _review_final_document(
            prepared,
            _backend(),
            tmp_path,
            _ExecutionMetrics(),
            service,  # type: ignore[arg-type]
        )
    )

    assert defects == []
    assert service.calls == [
        {"document_ref": "internal-document-ref"},
        {
            "document_ref": "internal-document-ref",
            "cursor": "internal-page-two",
        },
    ]
    assert len(service.receipts) == 2


def test_deterministic_renderer_failure_does_not_rotate_agent_backends(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backends = (_backend(), _backend())
    calls = 0

    async def fake_backend(*_args: Any, **_kwargs: Any) -> TemplateAgentExecution:
        nonlocal calls
        calls += 1
        raise ToolFailure(
            status="error",
            origin="renderer",
            code="libreoffice_conversion_failed",
            message="The fixed renderer could not convert the current Word.",
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.iter_agent_backends",
        lambda: iter(backends),
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_backend", fake_backend)

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(run_template_agent(prepared))

    assert caught.value.code == "libreoffice_conversion_failed"
    assert calls == 1


def test_visual_verdict_requires_exact_bound_pages() -> None:
    clean = {
        "pages": [
            {"page": 1, "verdict": "clean", "defects": []},
            {"page": 2, "verdict": "clean", "defects": []},
        ]
    }
    assert len(_validated_visual_pages(clean, {1, 2})) == 2

    with pytest.raises(ToolFailure) as caught:
        _validated_visual_pages(
            {"pages": [{"page": 1, "verdict": "clean", "defects": []}]},
            {1, 2},
        )

    assert caught.value.code == "visual_page_coverage_mismatch"


def test_agent_payload_hides_internal_refs_and_code_builds_them_back() -> None:
    public = _agent_payload(
        {
            "document_ref": "document:v1:hidden",
            "region_ref": "region:v1:hidden",
            "next_cursor": "hidden",
            "target": {
                "object_ref": {"object_id": "obj-0123456789abcdef01234567"},
                "text": "题目",
            },
        }
    )
    assert public == {
        "target": {
            "object_id": "obj-0123456789abcdef01234567",
            "text": "题目",
        }
    }

    translated = _translate_operation(
        {
            "action": "materialize_slot",
            "object_id": "obj-0123456789abcdef01234567",
            "field_id": "thesis.title.zh",
        }
    )
    assert translated["object_ref"] == {
        "object_id": "obj-0123456789abcdef01234567"
    }
    assert "object_id" not in translated


def test_cli_requirements_and_registry_are_optional() -> None:
    parsed = build_parser().parse_args(
        [
            "prepare-template",
            "--school-template",
            "school.docx",
            "--output",
            "task",
        ]
    )
    assert parsed.school_requirements is None
    assert parsed.field_registry is None


def test_run_prepare_template_accepts_application_publication_only(tmp_path: Path) -> None:
    async def fake_agent(prepared: Any) -> TemplateAgentExecution:
        output = prepared.task_root / "output/final-template.docx"
        shutil.copyfile(prepared.template_path, output)
        return TemplateAgentExecution(
            structured_output={
                "status": "ok",
                "published": True,
                "artifact_path": "output/final-template.docx",
                "template_sha256": sha256_file(output),
                "counts": COUNTS,
            },
            tool_uses=(
                "Skill",
                "mcp__docfit__template_get_current_work_item",
                "mcp__docfit__template_submit_current_decision",
                "mcp__docfit__template_get_review_batch",
            ),
            skills_loaded=("docfit-school-extract",),
            session_id="session-test",
            backend="minimax",
            num_turns=4,
            duration_ms=1200,
            duration_api_ms=900,
        )

    report = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert report.status == "built"
    assert Path(report.artifact_path).name == "final-template.docx"
    trace = Path(report.task_root) / "work/.docfit/template-agent-execution.json"
    assert trace.is_file()
    assert '"orchestrator": "application_owned"' in trace.read_text(encoding="utf-8")


def test_completed_resume_uses_cross_process_agent_evidence_without_rerunning(
    tmp_path: Path,
) -> None:
    calls = 0

    async def first_run(prepared: Any) -> TemplateAgentExecution:
        nonlocal calls
        calls += 1
        output = prepared.task_root / "output/final-template.docx"
        shutil.copyfile(prepared.template_path, output)
        for role, tool in (
            ("semantic", "mcp__docfit__template_get_current_work_item"),
            ("semantic", "mcp__docfit__template_submit_current_decision"),
        ):
            _append_agent_live_event(
                prepared,
                {
                    "event": "tool_use",
                    "role": role,
                    "backend": "minimax",
                    "tool": tool,
                    "input": {},
                },
            )
        return TemplateAgentExecution(
            structured_output={
                "status": "ok",
                "published": True,
                "artifact_path": "output/final-template.docx",
                "template_sha256": sha256_file(output),
                "counts": COUNTS,
            },
            tool_uses=("Skill", "mcp__docfit__template_get_review_batch"),
            skills_loaded=("docfit-school-extract",),
            session_id="visual-session",
            backend="minimax",
            num_turns=2,
            duration_ms=600,
            duration_api_ms=500,
        )

    first = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=first_run))

    async def must_not_run(_prepared: Any) -> TemplateAgentExecution:
        raise AssertionError("a completed checkpoint must not launch another Agent session")

    resumed = asyncio.run(
        run_prepare_template(_request(tmp_path), agent_runner=must_not_run)
    )

    assert calls == 1
    assert resumed.template_sha256 == first.template_sha256
    assert set(resumed.tool_uses) >= {
        "Skill",
        "mcp__docfit__template_get_current_work_item",
        "mcp__docfit__template_submit_current_decision",
        "mcp__docfit__template_get_review_batch",
    }
