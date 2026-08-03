"""Source-specific metadata projectors for O0 observation events."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
)

from docfit.observability.events import (
    ObservationActor,
    ObservationAttribute,
    ObservationError,
    ObservationEvent,
    ObservationEvidenceRef,
    ObservationPriority,
    ObservationSource,
    ProjectionContext,
    ProjectionRejected,
    ProjectionResult,
    SafeAttributeValue,
    project_safely,
)
from docfit.observability.report import project_conversion_report

_DOCFIT_TOOLS = {
    "mcp__docfit__docx_inspect": "docx_inspect",
    "mcp__docfit__docx_edit": "docx_edit",
    "mcp__docfit__docx_render": "docx_render",
    "mcp__docfit__docx_visual_review": "docx_visual_review",
    "mcp__docfit__docx_validate": "docx_validate",
}
_BUILTIN_TOOLS = {"Skill", "Agent", "AskUserQuestion"}
_KNOWN_TOOLS = set(_DOCFIT_TOOLS) | _BUILTIN_TOOLS
_KNOWN_SKILLS = {"convert-thesis", "docfit-school-extract"}
_KNOWN_SUBAGENTS = {"docfit-unit-analyst"}
_INSPECT_FOCUS = {
    "structure",
    "styles",
    "visible_objects",
    "template_rules",
    "thesis_content",
}
_EDIT_ACTIONS = {
    "replace_text",
    "apply_style",
    "set_properties",
    "import_template_sections",
}
_RENDER_INTENTS = {"baseline", "edit_feedback", "candidate_verification"}
_VISUAL_MODES = {"pages", "crops", "contact_sheet", "compare", "m0_image_smoke"}
_USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
}
_HASH_KEYS = {"source_sha256", "template_sha256", "requirements_sha256", "final_sha256"}


def _attrs(**values: SafeAttributeValue) -> tuple[ObservationAttribute, ...]:
    return tuple(
        ObservationAttribute(key, value)
        for key, value in values.items()
        if value is not None
    )


def _safe_identifier(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 256:
        return None
    if any(character in value for character in ("/", "\\", "\n", "\r", "\x00")):
        return None
    if not all(character.isalnum() or character in "_.:-" for character in value):
        return None
    return value


def _safe_code(value: object) -> str | None:
    identifier = _safe_identifier(value)
    if identifier is None or identifier.casefold() != identifier or len(identifier) > 128:
        return None
    return identifier


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _nonnegative_number(value: object) -> float | int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _hash(value: object) -> str | None:
    if (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    ):
        return value
    return None


def _source_id(value: object) -> str:
    identifier = _safe_identifier(value)
    if identifier is None:
        raise ProjectionRejected("observer_source_id_missing")
    return identifier


def _event(
    context: ProjectionContext,
    *,
    source_event_id: str,
    source: ObservationSource,
    kind: str,
    priority: ObservationPriority,
    actor: ObservationActor,
    summary_code: str,
    status: str | None = None,
    session_id: str | None = None,
    tool_name: str | None = None,
    tool_use_id: str | None = None,
    agent_id: str | None = None,
    agent_type: str | None = None,
    parent_tool_use_id: str | None = None,
    duration_ms: float | int | None = None,
    attributes: tuple[ObservationAttribute, ...] = (),
    evidence_refs: tuple[ObservationEvidenceRef, ...] = (),
    error: ObservationError | None = None,
) -> ObservationEvent:
    return ObservationEvent(
        schema_version=1,
        run_id=context.run_id,
        source_event_id=source_event_id,
        source_sequence=context.source_sequence,
        observed_at=context.observed_at,
        monotonic_offset_ms=context.monotonic_offset_ms,
        source=source,
        kind=kind,
        priority=priority,
        actor=actor,
        summary_code=summary_code,
        status=status,
        session_id=session_id,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        agent_id=agent_id,
        agent_type=agent_type,
        parent_tool_use_id=parent_tool_use_id,
        duration_ms=duration_ms,
        attributes=attributes,
        evidence_refs=evidence_refs,
        error=error,
    )


def _actor(
    *,
    agent_id: object = None,
    agent_type: object = None,
    parent_tool_use_id: object = None,
) -> ObservationActor:
    safe_agent_id = _safe_identifier(agent_id)
    safe_agent_type = _safe_identifier(agent_type)
    if safe_agent_id is not None or parent_tool_use_id is not None:
        return ObservationActor("subagent", safe_agent_id, safe_agent_type)
    return ObservationActor("main")


def _usage_attributes(usage: object) -> tuple[ObservationAttribute, ...]:
    if not isinstance(usage, Mapping):
        return ()
    values: dict[str, SafeAttributeValue] = {}
    for key in _USAGE_KEYS:
        value = _nonnegative_int(usage.get(key))
        if value is not None:
            values[key] = value
    return _attrs(**values)


def project_assistant_message(
    message: AssistantMessage,
    context: ProjectionContext,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        source_id = _source_id(message.message_id or message.uuid)
        parent_id = _safe_identifier(message.parent_tool_use_id)
        model = _safe_identifier(message.model)
        stop_reason = _safe_code(message.stop_reason)
        attributes = _usage_attributes(message.usage) + _attrs(
            model=model,
            block_count=len(message.content),
            stop_reason=stop_reason,
        )
        return _event(
            context,
            source_event_id=source_id,
            source="sdk",
            kind="assistant_message",
            priority="P1",
            actor=_actor(parent_tool_use_id=parent_id),
            summary_code="assistant_message_observed",
            status=_safe_code(message.error) or "ok",
            session_id=_safe_identifier(message.session_id),
            parent_tool_use_id=parent_id,
            attributes=attributes,
        )

    return project_safely(build)


def _object_refs(value: object) -> tuple[ObservationEvidenceRef, ...]:
    if not isinstance(value, Mapping):
        return ()
    document_hash = _hash(value.get("document_sha256"))
    object_id = value.get("object_id")
    if (
        document_hash is None
        or not isinstance(object_id, str)
        or not object_id.startswith("obj-")
    ):
        return ()
    return (
        ObservationEvidenceRef("document", document_hash),
        ObservationEvidenceRef("object", object_id, document_sha256=document_hash),
    )


def _tool_input_summary(
    tool_name: str,
    tool_input: object,
) -> tuple[tuple[ObservationAttribute, ...], tuple[ObservationEvidenceRef, ...]]:
    if not isinstance(tool_input, Mapping):
        return (), ()
    if tool_name == "Skill":
        skill = tool_input.get("skill") or tool_input.get("name")
        return _attrs(skill_name=skill if skill in _KNOWN_SKILLS else None), ()
    if tool_name == "Agent":
        subagent = tool_input.get("subagent_type")
        payload_bytes = len(
            json.dumps(tool_input, ensure_ascii=False, default=lambda _: None).encode("utf-8")
        )
        return _attrs(
            subagent_type=subagent if subagent in _KNOWN_SUBAGENTS else None,
            payload_bytes=payload_bytes,
        ), ()
    if tool_name == "AskUserQuestion":
        questions = tool_input.get("questions")
        question_count = len(questions) if isinstance(questions, list) else 0
        option_count = 0
        if isinstance(questions, list):
            option_count = sum(
                len(question.get("options", ()))
                for question in questions
                if isinstance(question, Mapping)
                and isinstance(question.get("options"), list)
            )
        return _attrs(question_count=question_count, option_count=option_count), ()
    logical = _DOCFIT_TOOLS.get(tool_name)
    if logical == "docx_inspect":
        focus = tool_input.get("focus")
        safe_focus = (
            tuple(item for item in focus if item in _INSPECT_FOCUS)
            if isinstance(focus, list)
            else ()
        )
        return _attrs(focus=safe_focus, focus_count=len(safe_focus)), ()
    if logical == "docx_edit":
        operations = tool_input.get("operations")
        actions: list[str] = []
        references: list[ObservationEvidenceRef] = []
        if isinstance(operations, list):
            for operation in operations[:256]:
                if not isinstance(operation, Mapping):
                    continue
                action = operation.get("action")
                if action in _EDIT_ACTIONS:
                    actions.append(action)
                references.extend(_object_refs(operation.get("target_ref")))
                references.extend(_object_refs(operation.get("insert_anchor_ref")))
                source_refs = operation.get("source_refs")
                if isinstance(source_refs, list):
                    for reference in source_refs[:256]:
                        references.extend(_object_refs(reference))
        counts = Counter(actions)
        action_counts = tuple(f"{key}:{counts[key]}" for key in sorted(counts))
        return _attrs(operation_count=len(actions), operation_types=action_counts), tuple(
            references[:256]
        )
    if logical == "docx_render":
        intent = tool_input.get("render_intent")
        focus_refs = tool_input.get("focus_object_refs")
        references = []
        if isinstance(focus_refs, list):
            for reference in focus_refs[:256]:
                references.extend(_object_refs(reference))
        return _attrs(
            render_intent=intent if intent in _RENDER_INTENTS else None,
            focus_ref_count=len(focus_refs) if isinstance(focus_refs, list) else 0,
        ), tuple(references[:256])
    if logical == "docx_visual_review":
        mode = tool_input.get("mode")
        pages = tool_input.get("pages")
        safe_pages = (
            tuple(
                page
                for page in pages[:256]
                if isinstance(page, int) and not isinstance(page, bool) and page >= 1
            )
            if isinstance(pages, list)
            else ()
        )
        crops = tool_input.get("crops")
        crop_pages = (
            tuple(
                page
                for crop in crops[:256]
                if isinstance(crop, Mapping)
                and isinstance((page := crop.get("page")), int)
                and not isinstance(page, bool)
                and page >= 1
            )
            if isinstance(crops, list)
            else ()
        )
        evidence = tuple(
            ObservationEvidenceRef("page", page)
            for page in dict.fromkeys((*safe_pages, *crop_pages))
        )
        return _attrs(
            mode=mode if mode in _VISUAL_MODES else None,
            page_count=len(safe_pages),
            crop_count=len(crop_pages),
        ), evidence
    if logical == "docx_validate":
        source_hash = _hash(tool_input.get("source_sha256"))
        evidence = (
            (ObservationEvidenceRef("document", source_hash),)
            if source_hash is not None
            else ()
        )
        task_rules = tool_input.get("task_rule_evidence")
        return _attrs(
            task_rule_count=len(task_rules) if isinstance(task_rules, list) else 0,
            required_visual_coverage=(
                "all_final_pages"
                if tool_input.get("required_visual_coverage") == "all_final_pages"
                else None
            ),
        ), evidence
    return (), ()


def project_tool_use_block(
    block: ToolUseBlock,
    context: ProjectionContext,
    *,
    session_id: str | None = None,
    parent_tool_use_id: str | None = None,
    agent_id: str | None = None,
    agent_type: str | None = None,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        if block.name not in _KNOWN_TOOLS:
            raise ProjectionRejected("observer_source_type_unsupported")
        tool_use_id = _source_id(block.id)
        attributes, evidence = _tool_input_summary(block.name, block.input)
        if block.name in _DOCFIT_TOOLS:
            attributes = (
                *attributes,
                *_attrs(
                    side_effect_possible=block.name
                    in {
                        "mcp__docfit__docx_edit",
                        "mcp__docfit__docx_render",
                    }
                ),
            )
        kind = {
            "Skill": "skill_use",
            "Agent": "subagent_use",
            "AskUserQuestion": "user_question_started",
        }.get(block.name, "tool_use")
        return _event(
            context,
            source_event_id=tool_use_id,
            source="sdk",
            kind=kind,
            priority="P1",
            actor=_actor(
                agent_id=agent_id,
                agent_type=agent_type,
                parent_tool_use_id=parent_tool_use_id,
            ),
            summary_code=f"{kind}_observed",
            status="started",
            session_id=_safe_identifier(session_id),
            tool_name=block.name,
            tool_use_id=tool_use_id,
            agent_id=_safe_identifier(agent_id),
            agent_type=_safe_identifier(agent_type),
            parent_tool_use_id=_safe_identifier(parent_tool_use_id),
            attributes=attributes,
            evidence_refs=evidence,
        )

    return project_safely(build)


def project_tool_result_block(
    block: ToolResultBlock,
    context: ProjectionContext,
    *,
    session_id: str | None = None,
    parent_tool_use_id: str | None = None,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        tool_use_id = _source_id(block.tool_use_id)
        return _event(
            context,
            source_event_id=tool_use_id,
            source="sdk",
            kind="tool_result",
            priority="P1",
            actor=_actor(parent_tool_use_id=parent_tool_use_id),
            summary_code="tool_result_observed",
            status="error" if block.is_error else "ok",
            session_id=_safe_identifier(session_id),
            tool_use_id=tool_use_id,
            parent_tool_use_id=_safe_identifier(parent_tool_use_id),
        )

    return project_safely(build)


def project_result_message(
    message: ResultMessage,
    context: ProjectionContext,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        source_id = _source_id(message.uuid or message.session_id)
        attributes = _usage_attributes(message.usage) + _attrs(
            num_turns=_nonnegative_int(message.num_turns),
            duration_api_ms=_nonnegative_int(message.duration_api_ms),
            total_cost_usd=_nonnegative_number(message.total_cost_usd),
            subtype=_safe_code(message.subtype),
            stop_reason=_safe_code(message.stop_reason),
            terminal_reason=_safe_code(message.terminal_reason),
            api_error_status=_nonnegative_int(message.api_error_status),
        )
        return _event(
            context,
            source_event_id=source_id,
            source="sdk",
            kind="sdk_result",
            priority="P0",
            actor=ObservationActor("main"),
            summary_code="sdk_result_observed",
            status="error" if message.is_error else "ok",
            session_id=_safe_identifier(message.session_id),
            duration_ms=_nonnegative_int(message.duration_ms),
            attributes=attributes,
        )

    return project_safely(build)


def _structured_response(value: object) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    structured = value.get("structuredContent")
    if isinstance(structured, Mapping):
        return structured
    if "status" in value:
        return value
    return None


def _common_result(
    payload: Mapping[str, Any],
) -> tuple[str, ObservationError | None, tuple[ObservationAttribute, ...]]:
    status = _safe_code(payload.get("status")) or "unknown"
    failure = payload.get("failure")
    error: ObservationError | None = None
    if isinstance(failure, Mapping):
        code = _safe_code(failure.get("code"))
        origin = _safe_code(failure.get("origin"))
        if code is not None and origin is not None:
            retryable = failure.get("retryable")
            error = ObservationError(
                code,
                origin,
                retryable if isinstance(retryable, bool) else None,
            )
    committed = payload.get("committed")
    return status, error, _attrs(
        committed=committed if isinstance(committed, bool) else None,
        warning_count=(
            len(payload.get("warnings", ()))
            if isinstance(payload.get("warnings"), list)
            else 0
        ),
        check_count=(
            len(payload.get("checks", ()))
            if isinstance(payload.get("checks"), list)
            else 0
        ),
    )


def _image_stats(response: object) -> tuple[int, int]:
    if not isinstance(response, Mapping) or not isinstance(response.get("content"), list):
        return 0, 0
    count = 0
    byte_count = 0
    for block in response["content"]:
        if not isinstance(block, Mapping) or block.get("type") != "image":
            continue
        data = block.get("data")
        if not isinstance(data, str):
            continue
        count += 1
        padding = 2 if data.endswith("==") else 1 if data.endswith("=") else 0
        byte_count += max(0, (len(data) * 3) // 4 - padding)
    return count, byte_count


def _tool_result_summary(
    tool_name: str,
    response: object,
) -> tuple[
    str,
    tuple[ObservationAttribute, ...],
    tuple[ObservationEvidenceRef, ...],
    ObservationError | None,
]:
    payload = _structured_response(response)
    if payload is None:
        return "unknown", (), (), None
    status, error, common = _common_result(payload)
    logical = _DOCFIT_TOOLS.get(tool_name)
    attributes: tuple[ObservationAttribute, ...] = ()
    evidence: list[ObservationEvidenceRef] = []
    artifact_published = False
    if logical == "docx_inspect":
        document = payload.get("document")
        document_hash = _hash(document.get("sha256")) if isinstance(document, Mapping) else None
        objects = payload.get("objects")
        risks = payload.get("risks")
        if document_hash is not None:
            evidence.append(ObservationEvidenceRef("document", document_hash))
        ref_count = 0
        if isinstance(objects, list):
            ref_count = sum(
                isinstance(item, Mapping) and isinstance(item.get("object_ref"), Mapping)
                for item in objects
            )
        attributes = _attrs(
            object_count=len(objects) if isinstance(objects, list) else 0,
            risk_count=len(risks) if isinstance(risks, list) else 0,
            object_ref_count=ref_count,
        )
    elif logical == "docx_edit":
        input_hash = _hash(payload.get("input_sha256"))
        output_hash = _hash(payload.get("output_sha256"))
        if input_hash is not None:
            evidence.append(ObservationEvidenceRef("document", input_hash))
        if output_hash is not None:
            evidence.append(ObservationEvidenceRef("document", output_hash))
        operations = payload.get("operations")
        actions = tuple(
            action
            for item in operations
            if isinstance(item, Mapping)
            and (action := item.get("action")) in _EDIT_ACTIONS
        ) if isinstance(operations, list) else ()
        attributes = _attrs(operation_count=len(actions), operation_types=actions)
        artifact_published = bool(
            status == "ok" and payload.get("committed") is True and output_hash is not None
        )
    elif logical == "docx_render":
        reference = payload.get("render_ref")
        if isinstance(reference, Mapping):
            document_hash = _hash(reference.get("document_sha256"))
            render_hash = _hash(reference.get("render_sha256"))
            provider = reference.get("provider")
            provider_name = (
                _safe_identifier(provider.get("name"))
                if isinstance(provider, Mapping)
                else None
            )
            if document_hash is not None:
                evidence.append(ObservationEvidenceRef("document", document_hash))
            if render_hash is not None:
                evidence.append(
                    ObservationEvidenceRef(
                        "render",
                        render_hash,
                        document_sha256=document_hash,
                    )
                )
            artifacts = reference.get("artifacts")
            attributes = _attrs(
                render_intent=(
                    reference.get("render_intent")
                    if reference.get("render_intent") in _RENDER_INTENTS
                    else None
                ),
                provider=provider_name,
                cache_hit=(
                    payload.get("cache_hit")
                    if isinstance(payload.get("cache_hit"), bool)
                    else None
                ),
                page_count=_nonnegative_int(reference.get("page_count")),
                dpi=_nonnegative_int(reference.get("dpi")),
                pdf_available=(
                    isinstance(artifacts.get("pdf"), str)
                    if isinstance(artifacts, Mapping)
                    else False
                ),
                pages_available=(
                    len(artifacts.get("pages", ()))
                    if isinstance(artifacts, Mapping)
                    and isinstance(artifacts.get("pages"), list)
                    else 0
                ),
            )
            artifact_published = status == "ok" and render_hash is not None
    elif logical == "docx_visual_review":
        document_hash = _hash(payload.get("document_sha256"))
        render_hash = _hash(payload.get("render_sha256"))
        if document_hash is not None:
            evidence.append(ObservationEvidenceRef("document", document_hash))
        if render_hash is not None:
            evidence.append(
                ObservationEvidenceRef(
                    "render", render_hash, document_sha256=document_hash
                )
            )
        raw_evidence = payload.get("evidence")
        pages: list[int] = []
        if isinstance(raw_evidence, list):
            for item in raw_evidence[:256]:
                if not isinstance(item, Mapping):
                    continue
                evidence_ref = _safe_code(item.get("evidence_ref"))
                page = _nonnegative_int(item.get("page"))
                if evidence_ref is not None:
                    evidence.append(
                        ObservationEvidenceRef(
                            "evidence",
                            evidence_ref,
                            document_sha256=document_hash,
                            render_sha256=render_hash,
                        )
                    )
                if page is not None and page >= 1:
                    pages.append(page)
                    evidence.append(
                        ObservationEvidenceRef(
                            "page",
                            page,
                            document_sha256=document_hash,
                            render_sha256=render_hash,
                        )
                    )
        image_count, image_bytes = _image_stats(response)
        attributes = _attrs(
            mode=payload.get("mode") if payload.get("mode") in _VISUAL_MODES else None,
            page_count=len(set(pages)),
            evidence_count=len(raw_evidence) if isinstance(raw_evidence, list) else 0,
            image_count=image_count,
            image_bytes=image_bytes,
        )
    elif logical == "docx_validate":
        source_hash = _hash(payload.get("source_sha256"))
        final_hash = _hash(payload.get("final_sha256"))
        if source_hash is not None:
            evidence.append(ObservationEvidenceRef("document", source_hash))
        if final_hash is not None:
            evidence.append(ObservationEvidenceRef("document", final_hash))
        summary = payload.get("summary")
        attributes = _attrs(
            errors=(
                _nonnegative_int(summary.get("errors"))
                if isinstance(summary, Mapping)
                else None
            ),
            issues=(
                _nonnegative_int(summary.get("issues"))
                if isinstance(summary, Mapping)
                else None
            ),
            warnings=(
                _nonnegative_int(summary.get("warnings"))
                if isinstance(summary, Mapping)
                else None
            ),
        )
    if logical is not None:
        attributes = (
            *attributes,
            *_attrs(
                side_effect_possible=logical in {"docx_edit", "docx_render"},
                artifact_published=artifact_published,
            ),
        )
    return status, common + attributes, tuple(evidence[:256]), error


def project_tool_hook(
    hook_input: Mapping[str, Any],
    context: ProjectionContext,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        phase = hook_input.get("hook_event_name")
        if phase not in {"PreToolUse", "PostToolUse", "PostToolUseFailure"}:
            raise ProjectionRejected("observer_source_type_unsupported")
        tool_name = hook_input.get("tool_name")
        if tool_name not in _KNOWN_TOOLS:
            raise ProjectionRejected("observer_source_type_unsupported")
        tool_use_id = _source_id(hook_input.get("tool_use_id"))
        agent_id = _safe_identifier(hook_input.get("agent_id"))
        agent_type = _safe_identifier(hook_input.get("agent_type"))
        status = "started"
        attributes: tuple[ObservationAttribute, ...] = ()
        evidence: tuple[ObservationEvidenceRef, ...] = ()
        error: ObservationError | None = None
        if phase == "PreToolUse":
            kind = "tool_pre"
            attributes, evidence = _tool_input_summary(tool_name, hook_input.get("tool_input"))
        elif phase == "PostToolUse":
            kind = "tool_post"
            status, attributes, evidence, error = _tool_result_summary(
                tool_name, hook_input.get("tool_response")
            )
        else:
            kind = "tool_failure"
            status = "error"
            interrupt = hook_input.get("is_interrupt")
            error = ObservationError(
                "sdk_tool_failure",
                "sdk",
                interrupt=interrupt if isinstance(interrupt, bool) else None,
            )
        return _event(
            context,
            source_event_id=tool_use_id,
            source="tool",
            kind=kind,
            priority="P0" if phase != "PreToolUse" else "P1",
            actor=_actor(agent_id=agent_id, agent_type=agent_type),
            summary_code=f"{kind}_observed",
            status=status,
            session_id=_safe_identifier(hook_input.get("session_id")),
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            agent_id=agent_id,
            agent_type=agent_type,
            attributes=attributes,
            evidence_refs=evidence,
            error=error,
        )

    return project_safely(build)


def project_subagent_hook(
    hook_input: Mapping[str, Any],
    context: ProjectionContext,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        phase = hook_input.get("hook_event_name")
        if phase not in {"SubagentStart", "SubagentStop"}:
            raise ProjectionRejected("observer_source_type_unsupported")
        agent_id = _source_id(hook_input.get("agent_id"))
        agent_type = _safe_identifier(hook_input.get("agent_type"))
        return _event(
            context,
            source_event_id=agent_id,
            source="sdk",
            kind="subagent_started" if phase == "SubagentStart" else "subagent_stopped",
            priority="P0",
            actor=ObservationActor("subagent", agent_id, agent_type),
            summary_code=(
                "subagent_started_observed"
                if phase == "SubagentStart"
                else "subagent_stopped_observed"
            ),
            status="started" if phase == "SubagentStart" else "finished",
            session_id=_safe_identifier(hook_input.get("session_id")),
            agent_id=agent_id,
            agent_type=agent_type,
            attributes=_attrs(
                stop_hook_active=(
                    hook_input.get("stop_hook_active")
                    if isinstance(hook_input.get("stop_hook_active"), bool)
                    else None
                )
            ),
        )

    return project_safely(build)


def project_permission_decision(
    context: ProjectionContext,
    *,
    tool_name: str,
    decision: Literal["allow", "deny"],
    tool_use_id: str | None = None,
    agent_id: str | None = None,
    subagent_type: str | None = None,
    reason_code: str = "permission_policy",
    question_count: int | None = None,
    option_count: int | None = None,
    answered: bool | None = None,
    duration_ms: float | None = None,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        if tool_name not in _KNOWN_TOOLS:
            raise ProjectionRejected("observer_source_type_unsupported")
        safe_tool_use_id = _safe_identifier(tool_use_id)
        source_id = safe_tool_use_id or f"permission-{context.source_sequence}"
        return _event(
            context,
            source_event_id=source_id,
            source="permission",
            kind="permission_decision",
            priority="P0",
            actor=_actor(agent_id=agent_id, agent_type=subagent_type),
            summary_code="permission_decision_observed",
            status=decision,
            tool_name=tool_name,
            tool_use_id=safe_tool_use_id,
            agent_id=_safe_identifier(agent_id),
            agent_type=(
                subagent_type if subagent_type in _KNOWN_SUBAGENTS else None
            ),
            duration_ms=_nonnegative_number(duration_ms),
            attributes=_attrs(
                reason_code=_safe_code(reason_code) or "permission_policy",
                question_count=_nonnegative_int(question_count),
                option_count=_nonnegative_int(option_count),
                answered=answered if isinstance(answered, bool) else None,
            ),
        )

    return project_safely(build)


def project_user_question(
    context: ProjectionContext,
    *,
    tool_use_id: str,
    tool_input: object,
    answered: bool | None,
    duration_ms: float | None = None,
    agent_id: str | None = None,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        safe_tool_use_id = _source_id(tool_use_id)
        attributes, _ = _tool_input_summary("AskUserQuestion", tool_input)
        attributes = (*attributes, *_attrs(answered=answered))
        return _event(
            context,
            source_event_id=safe_tool_use_id,
            source="permission",
            kind="user_question_finished" if answered is not None else "user_question_started",
            priority="P0",
            actor=_actor(agent_id=agent_id),
            summary_code="user_question_observed",
            status=(
                ("answered" if answered else "unanswered")
                if answered is not None
                else "started"
            ),
            tool_name="AskUserQuestion",
            tool_use_id=safe_tool_use_id,
            agent_id=_safe_identifier(agent_id),
            duration_ms=_nonnegative_number(duration_ms),
            attributes=attributes,
        )

    return project_safely(build)


def project_app_event(
    context: ProjectionContext,
    *,
    source_event_id: str,
    kind: Literal["run_started", "backend_started", "backend_finished", "run_finished"],
    status: str,
    task_ref: str | None = None,
    backend: str | None = None,
    model: str | None = None,
    attempt: int | None = None,
    hashes: Mapping[str, str] | None = None,
    failure_code: str | None = None,
    duration_ms: float | None = None,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        attributes: dict[str, SafeAttributeValue] = {}
        for key, value in (hashes or {}).items():
            if key in _HASH_KEYS and (safe_hash := _hash(value)) is not None:
                attributes[key] = safe_hash
        attributes.update(
            {
                "task_ref": _safe_identifier(task_ref),
                "backend": _safe_identifier(backend),
                "model": _safe_identifier(model),
                "attempt": _nonnegative_int(attempt),
            }
        )
        safe_failure_code = _safe_code(failure_code)
        safe_status = _safe_code(status) or "unknown"
        error = (
            ObservationError(safe_failure_code, "app")
            if safe_failure_code is not None
            else None
        )
        priority: ObservationPriority = (
            "P0"
            if kind in {"run_started", "run_finished"}
            or safe_failure_code is not None
            or safe_status in {"error", "needs_input", "failed"}
            else "P1"
        )
        return _event(
            context,
            source_event_id=_source_id(source_event_id),
            source="app",
            kind=kind,
            priority=priority,
            actor=ObservationActor("app"),
            summary_code=f"{kind}_observed",
            status=safe_status,
            duration_ms=_nonnegative_number(duration_ms),
            attributes=_attrs(**attributes),
            error=error,
        )

    return project_safely(build)


def project_report_event(
    report: Path | Mapping[str, Any],
    context: ProjectionContext,
) -> ProjectionResult:
    def build() -> ObservationEvent:
        projected = project_conversion_report(report)
        report_run_id = _safe_identifier(projected.get("run_id"))
        source_id = report_run_id or f"report-{context.source_sequence}"
        coverage = projected.get("observation_coverage")
        transcript = projected.get("sdk_transcript")
        attributes = _attrs(
            report_schema=_nonnegative_int(projected.get("schema_version")),
            report_run_id=report_run_id,
            task_ref=_safe_identifier(projected.get("task_ref")),
            association=_safe_code(projected.get("association")),
            backend=_safe_identifier(projected.get("backend")),
            knowledge_version=_safe_identifier(projected.get("knowledge_version")),
            knowledge_digest=_safe_identifier(projected.get("knowledge_digest")),
            tool_use_count=_nonnegative_int(projected.get("tool_use_count")),
            warning_count=_nonnegative_int(projected.get("warning_count")),
            coverage_state=(
                _safe_code(coverage.get("state"))
                if isinstance(coverage, Mapping)
                else None
            ),
            events_persisted=(
                _nonnegative_int(coverage.get("events_persisted"))
                if isinstance(coverage, Mapping)
                else None
            ),
            events_dropped=(
                _nonnegative_int(coverage.get("events_dropped"))
                if isinstance(coverage, Mapping)
                else None
            ),
            transcript_status=(
                _safe_code(transcript.get("status"))
                if isinstance(transcript, Mapping)
                else None
            ),
            transcript_residual_count=(
                _nonnegative_int(transcript.get("residual_count"))
                if isinstance(transcript, Mapping)
                else None
            ),
        )
        evidence = tuple(
            ObservationEvidenceRef("document", document_hash)
            for key in (
                "source_sha256",
                "template_sha256",
                "requirements_sha256",
                "final_sha256",
            )
            if (document_hash := _hash(projected.get(key))) is not None
        )
        return _event(
            context,
            source_event_id=source_id,
            source="report",
            kind="conversion_report",
            priority="P0",
            actor=ObservationActor("app"),
            summary_code="conversion_report_observed",
            status=_safe_code(str(projected.get("status")).casefold()) or "unknown",
            session_id=_safe_identifier(projected.get("session_id")),
            attributes=attributes,
            evidence_refs=evidence,
        )

    return project_safely(build)


def with_additional_attributes(
    result: ProjectionResult,
    attributes: Sequence[ObservationAttribute],
) -> ProjectionResult:
    """Test/composition helper that still re-enters the bounded event validator."""

    if result.event is None:
        return result
    event = result.event
    return project_safely(
        lambda: replace(
            event,
            attributes=(*event.attributes, *tuple(attributes)),
        )
    )
