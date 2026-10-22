"""Deterministic materialization from Harness-accepted Word fragments."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.body_interfaces import body_interfaces, body_paragraph_carrier
from docfit.template.materialization.executor import write_materialized_docx
from docfit.template.materialization.handlers.body_structure import materialize_body_structure
from docfit.template.materialization.handlers.cleanup import exact_shape_cleanup_locator
from docfit.template.materialization.handlers.generated_content import (
    generated_content_policy_receipts,
)
from docfit.template.materialization.handlers.slots import (
    IndexedSemanticPart,
    first_run_properties,
    materialize_slot_paragraph,
    replace_paragraph_content,
    run,
)
from docfit.template.materialization.handlers.table_manual_cells import (
    manual_table_cell_policy_receipts,
)
from docfit.template.materialization.models import (
    AcceptedResolvedSpan,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
)
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.materialization.receipts import build_materialization_receipts
from docfit.template.materialization.recovery import readiness_failure
from docfit.template.unit_source import source_unit_cut_points, validate_inventory_partition
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json
from docfit.tools.word_parts import WordStory, read_word_stories, resolve_story_locator
from docfit.tools.word_xml import serialize_word_xml, visible_word_text

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{W_NS}}}"


@dataclass(frozen=True)
class _ExactSpanTarget:
    span: AcceptedResolvedSpan
    story: WordStory
    paragraph: ET.Element | None
    body_block: ET.Element | None
    existing_control: ET.Element | None
    shape: ET.Element | None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parent_map(document: ET.Element) -> dict[int, ET.Element]:
    return {id(child): parent for parent in document.iter() for child in list(parent)}


def _ancestor(
    element: ET.Element,
    parents: dict[int, ET.Element],
    local_name: str,
) -> ET.Element | None:
    current: ET.Element | None = element
    while current is not None:
        if _local_name(current.tag) == local_name:
            return current
        current = parents.get(id(current))
    return None


def _visible_text(element: ET.Element) -> str:
    return visible_word_text(element)


def _fragment_text_is_current(element: ET.Element, fragment: JsonObject) -> bool:
    extent = fragment.get("extent")
    if extent == {"kind": "whole_entry"}:
        return True
    start = fragment.get("object_text_start")
    end = fragment.get("object_text_end")
    text = fragment.get("text")
    return (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and isinstance(text, str)
        and _visible_text(element)[start:end] == text
    )


def _top_level_body_block(
    element: ET.Element,
    parents: dict[int, ET.Element],
) -> ET.Element | None:
    current = element
    parent = parents.get(id(current))
    while parent is not None and _local_name(parent.tag) != "body":
        current = parent
        parent = parents.get(id(current))
    if parent is None or _local_name(current.tag) not in {"p", "tbl"}:
        return None
    return current


def _resolve_all_span_targets(
    *,
    stories: dict[str, WordStory],
    plan: MaterializationPlan,
) -> dict[str, _ExactSpanTarget]:
    """Resolve every accepted fragment before the first mutation."""

    result: dict[str, _ExactSpanTarget] = {}
    for intent in plan.intents:
        for span in intent.resolved_spans:
            if span.span_ref in result:
                continue
            paragraphs: list[ET.Element] = []
            body_blocks: list[ET.Element] = []
            controls: list[ET.Element] = []
            shapes: list[ET.Element] = []
            span_story: WordStory | None = None
            for fragment in span.word_fragments:
                locator = fragment.get("locator")
                resolved = (
                    resolve_story_locator(stories, locator)
                    if isinstance(locator, str) and locator.strip()
                    else None
                )
                if resolved is None:
                    raise _stale_fragment_failure(span)
                story, target = resolved
                if (
                    span_story is not None
                    and span_story.part_name != story.part_name
                    or not _fragment_text_is_current(target, fragment)
                ):
                    raise _stale_fragment_failure(span)
                span_story = story
                if target.tag == "{urn:schemas-microsoft-com:vml}shape" and target not in shapes:
                    shapes.append(target)
                parents = _parent_map(story.root)
                paragraph = _ancestor(target, parents, "p")
                if paragraph is not None and paragraph not in paragraphs:
                    paragraphs.append(paragraph)
                body_block = _top_level_body_block(target, parents)
                if body_block is not None and body_block not in body_blocks:
                    body_blocks.append(body_block)
                control = _ancestor(target, parents, "sdt")
                if control is not None and control not in controls:
                    controls.append(control)
            paragraph = paragraphs[0] if len(paragraphs) == 1 else None
            body_block = body_blocks[0] if len(body_blocks) == 1 else None
            control = controls[0] if len(controls) == 1 else None
            if span_story is None:
                raise _stale_fragment_failure(span)
            result[span.span_ref] = _ExactSpanTarget(
                span=span,
                story=span_story,
                paragraph=paragraph,
                body_block=body_block,
                existing_control=control,
                shape=shapes[0] if len(shapes) == 1 else None,
            )
    return result


def _stale_fragment_failure(span: AcceptedResolvedSpan) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="harness",
        code="materialization_word_fragment_stale",
        message="An accepted Word fragment no longer resolves to its exact source content.",
        retryable=True,
        suggested_actions=(
            "Refresh source inventory and semantic judgments before materialization.",
            f"span_ref={span.span_ref}",
        ),
    )


def _ensure_source_document_hash_current(
    *, source_docx: Path, inventory: JsonObject, review: JsonObject
) -> str:
    current = sha256_file(source_docx)
    inventory_hash = inventory.get("document_sha256")
    review_hash = review.get("document_sha256")
    if inventory_hash != current or review_hash != current:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="stale_ref",
            message="Source DOCX, inventory, and accepted review must name one current snapshot.",
            retryable=True,
            suggested_actions=("Refresh the source inventory and semantic review.",),
        )
    return current


def _part(span: AcceptedResolvedSpan) -> JsonObject:
    result: JsonObject = {"text": span.text, "role": span.role}
    if span.field_id is not None:
        result["field_id"] = span.field_id
    return result


def _indexed_parts(intent: MaterializationIntent) -> list[IndexedSemanticPart]:
    return [(span.part_index, _part(span)) for span in intent.resolved_spans]


def _operation_provenance(span: AcceptedResolvedSpan) -> JsonObject:
    return {
        "source_entry_id": span.source_entry_id,
        "span_ref": span.span_ref,
        "word_fragments": [dict(fragment) for fragment in span.word_fragments],
    }


def _paragraph_for_intent(
    intent: MaterializationIntent,
    targets: dict[str, _ExactSpanTarget],
) -> ET.Element:
    paragraphs = {
        id(target.paragraph): target.paragraph
        for span in intent.resolved_spans
        if (target := targets[span.span_ref]).paragraph is not None
    }
    if len(paragraphs) != 1:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="materialization_span_crosses_paragraph_carriers",
            message="One paragraph mutation intent must resolve to exactly one Word paragraph.",
        )
    return next(iter(paragraphs.values()))


def _paragraph_parent(document: ET.Element, paragraph: ET.Element) -> ET.Element | None:
    return next((item for item in document.iter() if paragraph in list(item)), None)


def _paragraph_is_in_vertically_centered_table_cell(
    document: ET.Element,
    paragraph: ET.Element,
) -> bool:
    cell = _ancestor(paragraph, _parent_map(document), "tc")
    alignment = cell.find(f"{_W}tcPr/{_W}vAlign") if cell is not None else None
    return alignment is not None and alignment.get(f"{_W}val") == "center"


def _adopt_existing_sdt_slots(
    *,
    control: ET.Element,
    block_id: str,
    registry: FieldRegistrySnapshot,
    indexed_ordered_parts_for_block: list[IndexedSemanticPart],
    resolved_spans: list[JsonObject],
) -> list[JsonObject]:
    slot_parts = [
        item for item in indexed_ordered_parts_for_block if item[1].get("role") == "fill_slot"
    ]
    if len(slot_parts) != 1:
        raise ToolFailure(
            status="needs_input",
            origin="postcondition",
            code="materialization_existing_sdt_slot_ambiguous",
            message="One accepted content control can carry exactly one fill slot.",
        )
    part_index, part = slot_parts[0]
    field_id = part.get("field_id")
    span = next(
        (
            item
            for item in resolved_spans
            if item.get("part_index") == part_index and item.get("field_id") == field_id
        ),
        None,
    )
    if not isinstance(field_id, str) or span is None:
        raise ToolFailure(
            status="needs_input",
            origin="postcondition",
            code="materialization_slot_ref_missing",
            message="Accepted fill slot is missing its typed field binding.",
        )
    span_ref = span.get("span_ref")
    slot_ref = span.get("slot_ref")
    if not isinstance(span_ref, str) or slot_ref != f"{span_ref};field_id={field_id}":
        raise ToolFailure(
            status="needs_input",
            origin="postcondition",
            code="materialization_slot_ref_missing",
            message="Accepted fill slot has a mismatched slot_ref.",
        )
    properties = control.find(f"{_W}sdtPr")
    if properties is None:
        properties = ET.Element(f"{_W}sdtPr")
        control.insert(0, properties)
    for name, value in (
        ("alias", field_id),
        ("tag", str(span["slot_ref"])),
        ("id", str(int(sha256_json({"slot_ref": span["slot_ref"]})[:7], 16))),
    ):
        node = properties.find(f"{_W}{name}")
        if node is None:
            node = ET.SubElement(properties, f"{_W}{name}")
        node.set(f"{_W}val", value)
    content_type = registry.lookup(field_id).get("content_type")
    if content_type not in {"rich_text", "section"} and properties.find(f"{_W}text") is None:
        ET.SubElement(properties, f"{_W}text")
    return [
        {
            "action": "materialize_slot",
            "target": "existing_sdt",
            "field_id": field_id,
            "block_id": block_id,
            "part_index": part_index,
            "span_ref": span["span_ref"],
            "slot_ref": span["slot_ref"],
            **(
                {"source_entry_id": span["source_entry_id"]}
                if isinstance(span.get("source_entry_id"), str)
                else {}
            ),
            **(
                {"word_fragments": span["word_fragments"]}
                if isinstance(span.get("word_fragments"), list)
                else {}
            ),
        }
    ]


def _materialize_slot_intent(
    *,
    document: ET.Element,
    intent: MaterializationIntent,
    targets: dict[str, _ExactSpanTarget],
    registry: FieldRegistrySnapshot,
) -> tuple[list[JsonObject], JsonObject | None]:
    paragraph = _paragraph_for_intent(intent, targets)
    controls = {
        id(control): control
        for span in intent.resolved_spans
        if (control := targets[span.span_ref].existing_control) is not None
    }
    spans_json = [span.to_json() for span in intent.resolved_spans]
    if controls:
        if len(controls) != 1:
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="materialization_existing_sdt_target_mismatch",
                message="Accepted fragments resolve to more than one content control.",
            )
        operations = _adopt_existing_sdt_slots(
            control=next(iter(controls.values())),
            block_id=intent.resolved_spans[0].source_entry_id,
            registry=registry,
            indexed_ordered_parts_for_block=_indexed_parts(intent),
            resolved_spans=spans_json,
        )
    else:
        operations = materialize_slot_paragraph(
            paragraph=paragraph,
            block_id=intent.resolved_spans[0].source_entry_id,
            registry=registry,
            indexed_ordered_parts=_indexed_parts(intent),
            resolved_spans=spans_json,
            compact_placeholders=_paragraph_is_in_vertically_centered_table_cell(
                document, paragraph
            ),
        )
    spans_by_ref = {span.span_ref: span for span in intent.resolved_spans}
    for operation in operations:
        span_ref = operation.get("span_ref")
        if isinstance(span_ref, str) and span_ref in spans_by_ref:
            operation.update(_operation_provenance(spans_by_ref[span_ref]))
        operation["judgment_refs"] = list(intent.source_judgment_refs)
    cleanup_spans = [
        span
        for span in intent.resolved_spans
        if span.role == "cleanup" or (span.role == "style_only" and span.text)
    ]
    cleanup = (
        {
            "action": "remove_exact_fragments",
            "block_id": intent.resolved_spans[0].source_entry_id,
            "source_entry_id": intent.resolved_spans[0].source_entry_id,
            "judgment_refs": list(intent.source_judgment_refs),
            "span_refs": [span.span_ref for span in cleanup_spans],
            "word_fragments": [
                dict(fragment) for span in cleanup_spans for fragment in span.word_fragments
            ],
        }
        if cleanup_spans
        else None
    )
    return operations, cleanup


def _remove_exact_cleanup_intent(
    *,
    document: ET.Element,
    intent: MaterializationIntent,
    targets: dict[str, _ExactSpanTarget],
    removed_carriers: set[int],
) -> JsonObject:
    carrier, carrier_kind = _cleanup_carrier_for_intent(intent, targets)
    selected = "".join(span.text for span in intent.resolved_spans)
    already_removed = id(carrier) in removed_carriers
    if not already_removed and carrier_kind in {"paragraph", "shape"} and (
        selected != _visible_text(carrier)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code=f"cleanup_span_not_whole_{carrier_kind}",
            message=(
                "Deletion requires accepted fragments covering the selected carrier exactly."
            ),
        )
    if already_removed:
        shared_carrier = True
    else:
        parent = _paragraph_parent(document, carrier)
        if parent is None:
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="cleanup_target_unexecutable",
                message="Accepted cleanup paragraph has no writable parent.",
            )
        parent.remove(carrier)
        if parent.tag == f"{_W}tc" and (not list(parent) or list(parent)[-1].tag != f"{_W}p"):
            # A Word table cell must end with a paragraph.  Cleanup can remove
            # its only (or trailing) example paragraph; leaving ``w:tc`` empty
            # makes Microsoft Word repair the generated document on open.
            parent.append(ET.Element(f"{_W}p"))
        elif _local_name(parent.tag) in {
            "hdr",
            "ftr",
            "footnote",
            "endnote",
            "comment",
        } and not any(_local_name(child.tag) in {"p", "tbl", "sdt"} for child in parent):
            parent.append(ET.Element(f"{_W}p"))
        removed_carriers.add(id(carrier))
        shared_carrier = False
    result: JsonObject = {
        "action": f"remove_{carrier_kind}",
        "block_id": intent.resolved_spans[0].source_entry_id,
        "source_entry_id": intent.resolved_spans[0].source_entry_id,
        "judgment_refs": list(intent.source_judgment_refs),
        "span_refs": [span.span_ref for span in intent.resolved_spans],
        "word_fragments": [
            dict(fragment) for span in intent.resolved_spans for fragment in span.word_fragments
        ],
    }
    if shared_carrier:
        result["shared_carrier_already_removed"] = True
    return result


def _cleanup_carrier_for_intent(
    intent: MaterializationIntent,
    targets: dict[str, _ExactSpanTarget],
) -> tuple[ET.Element, str]:
    if exact_shape_cleanup_locator(intent) is not None:
        shapes = [targets[span.span_ref].shape for span in intent.resolved_spans]
        if shapes and shapes[0] is not None and all(shape is shapes[0] for shape in shapes):
            return shapes[0], "shape"
        raise ToolFailure(
            status="error", origin="tool", code="cleanup_shape_target_unexecutable",
            message="The accepted shape does not resolve to one exact writable shape.",
            retryable=False,
        )
    paragraphs = {
        id(target.paragraph): target.paragraph
        for span in intent.resolved_spans
        if (target := targets[span.span_ref]).paragraph is not None
    }
    if len(paragraphs) == 1:
        return next(iter(paragraphs.values())), "paragraph"
    body_blocks = {
        id(target.body_block): target.body_block
        for span in intent.resolved_spans
        if (target := targets[span.span_ref]).body_block is not None
    }
    if (
        not paragraphs
        and len(body_blocks) == 1
        and (table := next(iter(body_blocks.values()))).tag == f"{_W}tbl"
        and all(_span_is_top_level_table_whole_entry(span) for span in intent.resolved_spans)
    ):
        return table, "table"
    raise ToolFailure(
        status="needs_input",
        origin="harness",
        code="materialization_span_crosses_paragraph_carriers",
        message="One cleanup intent must resolve to one exact writable Word carrier.",
    )


def _span_is_top_level_table_whole_entry(span: AcceptedResolvedSpan) -> bool:
    return bool(span.word_fragments) and all(
        fragment.get("extent") == {"kind": "whole_entry"}
        and isinstance(locator := fragment.get("locator"), str)
        and len(segments := [segment for segment in locator.split("/") if segment]) == 2
        and segments[0] == "body"
        and segments[1].startswith("tbl[")
        for fragment in span.word_fragments
    )


def _rewrite_non_slot_intent(
    *, intent: MaterializationIntent, targets: dict[str, _ExactSpanTarget]
) -> JsonObject | None:
    removed_spans = [
        span
        for span in intent.resolved_spans
        if span.role in {"cleanup", "style_only"} and span.text
    ]
    if not removed_spans:
        return None
    paragraph = _paragraph_for_intent(intent, targets)
    kept_text = "".join(
        span.text for span in intent.resolved_spans if span.role not in {"cleanup", "style_only"}
    )
    if kept_text == _visible_text(paragraph):
        return None
    replace_paragraph_content(paragraph, [run(kept_text, first_run_properties(paragraph))])
    return {
        "action": "remove_exact_fragments",
        "block_id": intent.resolved_spans[0].source_entry_id,
        "source_entry_id": intent.resolved_spans[0].source_entry_id,
        "judgment_refs": list(intent.source_judgment_refs),
        "span_refs": [span.span_ref for span in removed_spans],
        "word_fragments": [
            dict(fragment) for span in removed_spans for fragment in span.word_fragments
        ],
    }


def _materialize_body_intents(
    *,
    document: ET.Element,
    inventory: JsonObject,
    plan: MaterializationPlan,
    targets: dict[str, _ExactSpanTarget],
    registry: FieldRegistrySnapshot,
) -> tuple[list[JsonObject], list[JsonObject]]:
    body_intents = tuple(
        intent
        for intent in plan.intents
        if intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
    )
    if not body_intents:
        return [], []
    by_source_entry: dict[str, ET.Element] = {}
    groups: dict[int, list[MaterializationIntent]] = {}
    parents = _parent_map(document)
    for intent in body_intents:
        intent_parents: set[int] = set()
        for span in intent.resolved_spans:
            target = targets[span.span_ref]
            exact_paragraph = all(
                body_paragraph_carrier(fragment.get("locator")) is not None
                for fragment in span.word_fragments
            )
            carrier = target.paragraph if exact_paragraph else target.body_block
            if carrier is not None:
                by_source_entry[span.source_entry_id] = carrier
                parent = parents.get(id(carrier))
                if parent is not None:
                    intent_parents.add(id(parent))
        if len(intent_parents) != 1:
            raise _body_execution_failure()
        groups.setdefault(next(iter(intent_parents)), []).append(intent)
    operations: list[JsonObject] = []
    cleanup: list[JsonObject] = []
    for intents in groups.values():
        group_operations, group_cleanup, _ = materialize_body_structure(
            document=document, by_block=by_source_entry, registry=registry,
            inventory=inventory, plan=replace(plan, intents=tuple(intents)), removed=set(),
        )
        if not group_operations:
            raise _body_execution_failure()
        operations.extend(group_operations)
        cleanup.extend(group_cleanup)
    spans_by_ref = {
        span.span_ref: span for intent in body_intents for span in intent.resolved_spans
    }
    for item in [*operations, *cleanup]:
        members = item.get("members")
        if isinstance(members, list):
            for member in members:
                if not isinstance(member, dict):
                    continue
                member_ref = member.get("span_ref")
                if isinstance(member_ref, str) and member_ref in spans_by_ref:
                    member["word_fragments"] = [
                        dict(fragment) for fragment in spans_by_ref[member_ref].word_fragments
                    ]
        refs = [item.get("span_ref"), *cast(list[object], item.get("span_refs", []))]
        matched = [
            spans_by_ref[ref] for ref in refs if isinstance(ref, str) and ref in spans_by_ref
        ]
        item["word_fragments"] = [
            dict(fragment) for span in matched for fragment in span.word_fragments
        ]
    return operations, cleanup


def _body_execution_failure() -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="tool",
        code="body_structure_materialization_unexecutable",
        message="Accepted body-structure fragments produced no exact Word mutation.",
    )


def _selected_body_table_containers(
    *, plan: MaterializationPlan, targets: dict[str, _ExactSpanTarget]
) -> tuple[ET.Element, ...]:
    containers: dict[int, ET.Element] = {}
    for intent in plan.intents:
        if intent.intent_type != MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE:
            continue
        for span in intent.resolved_spans:
            if span.role != "body_structure" or not _span_is_top_level_table_whole_entry(span):
                continue
            target = targets[span.span_ref].body_block
            if target is not None and target.tag == f"{_W}tbl":
                containers[id(target)] = target
    return tuple(containers.values())


def _intent_is_inside_body_table(
    *,
    intent: MaterializationIntent,
    targets: dict[str, _ExactSpanTarget],
    containers: tuple[ET.Element, ...],
) -> bool:
    paragraphs = {
        id(target.paragraph): target.paragraph
        for span in intent.resolved_spans
        if (target := targets[span.span_ref]).paragraph is not None
    }
    return bool(paragraphs) and all(
        any(item is paragraph for container in containers for item in container.iter())
        for paragraph in paragraphs.values()
    )


def _serialize(root: ET.Element) -> bytes:
    return serialize_word_xml(root)


def _texts_by_source_entry(
    *,
    plan: MaterializationPlan,
    targets: dict[str, _ExactSpanTarget],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for intent in plan.intents:
        for span in intent.resolved_spans:
            target = targets[span.span_ref]
            carrier = target.shape if target.shape is not None else target.paragraph
            if carrier is not None:
                attached = any(item is carrier for item in target.story.root.iter())
                result[span.source_entry_id] = _visible_text(carrier) if attached else ""
    return result


def _preservation_policy_receipts(
    plan: MaterializationPlan, *, cleanup: list[JsonObject]
) -> list[JsonObject]:
    handlers = {
        MaterializationIntentType.KEEP_FIXED_CONTENT: "fixed_content",
        MaterializationIntentType.TRANSFER_STYLE_ONLY: "style_only",
        MaterializationIntentType.NO_OP: "no_op",
    }
    mutated_judgment_refs = {
        ref
        for item in cleanup
        for ref in cast(list[object], item.get("judgment_refs", []))
        if isinstance(ref, str)
    }
    return [
        {
            "action": "preserve_exact_fragments",
            "handler": handlers[intent.intent_type],
            "intent_ref": intent.intent_ref,
            "source_judgment_refs": list(intent.source_judgment_refs),
            "scope_refs": [scope.to_json() for scope in intent.scope_refs],
            "span_refs": [span.span_ref for span in intent.resolved_spans],
            "resolved_spans": [span.to_json() for span in intent.resolved_spans],
            "word_fragments": [
                dict(fragment) for span in intent.resolved_spans for fragment in span.word_fragments
            ],
            "mutation": "none",
            "actual_result": "preserved",
        }
        for intent in plan.intents
        if intent.intent_type in handlers
        and not mutated_judgment_refs.intersection(intent.source_judgment_refs)
    ]


def materialize_template_from_semantics(
    *,
    source_docx: Path,
    output_docx: Path,
    registry: FieldRegistrySnapshot,
    inventory: JsonObject,
    review: JsonObject,
) -> JsonObject:
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    if feedback is not None:
        raise readiness_failure(feedback)
    current_document_sha256 = _ensure_source_document_hash_current(
        source_docx=source_docx, inventory=inventory, review=review
    )
    compiled = build_shadow_materialization_plan(
        inventory=inventory, review=review, registry=registry
    )
    if not compiled.ready:
        raise ToolFailure(
            status="error",
            origin="harness",
            code="template_materialization_system_state_invalid",
            message="Accepted semantic review did not compile to one typed plan.",
            retryable=False,
        )
    plan = compiled.plan
    with zipfile.ZipFile(source_docx) as archive:
        stories = read_word_stories(archive)
    document = stories["body"].root
    original_parts = {story.part_name: _serialize(story.root) for story in stories.values()}
    targets = _resolve_all_span_targets(stories=stories, plan=plan)
    body_table_containers = _selected_body_table_containers(plan=plan, targets=targets)
    before_text = _texts_by_source_entry(plan=plan, targets=targets)

    operations, cleanup = _materialize_body_intents(
        document=document, inventory=inventory, plan=plan, targets=targets, registry=registry
    )
    removed_cleanup_carriers: set[int] = set()
    for intent in plan.intents:
        if intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE:
            continue
        if intent.intent_type == MaterializationIntentType.MATERIALIZE_SLOT:
            slot_operations, slot_cleanup = _materialize_slot_intent(
                document=targets[intent.resolved_spans[0].span_ref].story.root,
                intent=intent,
                targets=targets,
                registry=registry,
            )
            operations.extend(slot_operations)
            if slot_cleanup is not None:
                cleanup.append(slot_cleanup)
        elif intent.intent_type == MaterializationIntentType.DELETE_BLOCK:
            cleanup.append(
                _remove_exact_cleanup_intent(
                    document=targets[intent.resolved_spans[0].span_ref].story.root,
                    intent=intent,
                    targets=targets,
                    removed_carriers=removed_cleanup_carriers,
                )
            )
        elif intent.intent_type in {
            MaterializationIntentType.KEEP_FIXED_CONTENT,
            MaterializationIntentType.TRANSFER_STYLE_ONLY,
            MaterializationIntentType.REFRESH_GENERATED_CONTENT,
        }:
            if _intent_is_inside_body_table(
                intent=intent,
                targets=targets,
                containers=body_table_containers,
            ):
                continue
            item = _rewrite_non_slot_intent(intent=intent, targets=targets)
            if item is not None:
                cleanup.append(item)

    cut_points = source_unit_cut_points(validate_inventory_partition(inventory))
    expected_slots = {
        binding.slot_ref
        for intent in plan.intents
        if intent.intent_type != MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
        for binding in intent.field_bindings if binding.role == "fill_slot"
    }
    expected_slots.update(
        group.slot_ref
        for intent in plan.intents
        if intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
        for group in body_interfaces(intent.resolved_spans, cut_points=cut_points)
    )
    actual_slots = {
        str(item["slot_ref"])
        for item in operations
        if item.get("action") == "materialize_slot" and isinstance(item.get("slot_ref"), str)
    }
    actual_slots.update(
        str(member["slot_ref"])
        for item in operations
        for member in cast(list[JsonObject], item.get("members", []))
        if isinstance(member, dict) and isinstance(member.get("slot_ref"), str)
    )
    if expected_slots != actual_slots:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="slot_materialization_unexecutable",
            message="Not every accepted field binding produced its exact slot_ref.",
        )

    after_text = _texts_by_source_entry(plan=plan, targets=targets)
    policies = [
        *manual_table_cell_policy_receipts(plan),
        *generated_content_policy_receipts(plan),
        *_preservation_policy_receipts(plan, cleanup=cleanup),
    ]
    receipts = build_materialization_receipts(
        plan=plan,
        operations=operations,
        cleanup=cleanup,
        policy_receipts=policies,
        before_text_by_block=before_text,
        after_text_by_block=after_text,
    )
    write = write_materialized_docx(
        source_docx=source_docx,
        output_docx=output_docx,
        document_xml=_serialize(document),
        part_updates={
            story.part_name: serialized
            for story in stories.values()
            if (serialized := _serialize(story.root)) != original_parts[story.part_name]
        },
    )
    return {
        "schema_version": 2,
        "status": "ok",
        "document_sha256": current_document_sha256,
        "source_inventory_digest": review.get("source_inventory_digest"),
        "unit_projection_digest": review.get("unit_projection_digest"),
        "semantic_judgments_sha256": review.get("semantic_judgments_sha256"),
        "field_vocabulary_digest": review.get("field_vocabulary_digest"),
        "field_registry_ref": registry.identity(),
        "operation_count": len(operations),
        "cleanup_count": len(cleanup),
        "operations": operations,
        "cleanup": cleanup,
        "policy_receipts": policies,
        "mutation_receipts": receipts,
        "receipt_count": len(receipts),
        "write": write,
        "shadow_intent_plan": compiled.to_json(),
    }
