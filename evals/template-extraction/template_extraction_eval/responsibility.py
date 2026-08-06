"""Build and compare the exhaustive document-fact responsibility surface.

The unit of coverage is every semantic fact emitted by ``DocumentFacts``.  A
managed content-control fact belongs to the slot view; an explicitly removed
region belongs to remove; every remaining fact is protected by complement.
This prevents a short list of protected anchors from masquerading as a full
document preservation score.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from .facts.effective_style import style_differences
from .markers import managed_marker_tags, marker_expectations
from .models import (
    AssertionResult,
    AssertionStatus,
    DocumentFacts,
    EffectiveStyle,
    EvalConfig,
    FillContract,
    Owner,
    ResponsibilityAtom,
    ResponsibilityInventory,
    View,
    stable_data,
)

POLICY = "exhaustive-semantic-document-facts/v1"


def _paragraph_key(part: str, story: str, paragraph_index: int) -> tuple[str, str, int]:
    return part, story, paragraph_index


def _overlaps(start: int, end: int, interval_start: int, interval_end: int) -> bool:
    if start == end:
        return interval_start <= start < interval_end
    return start < interval_end and end > interval_start


def _masked_text(text: str, intervals: list[tuple[int, int]]) -> str:
    if not intervals:
        return text
    result: list[str] = []
    cursor = 0
    for start, end in sorted(intervals):
        bounded_start = max(cursor, min(len(text), start))
        bounded_end = max(bounded_start, min(len(text), end))
        result.append(text[cursor:bounded_start])
        result.append("<SLOT>")
        cursor = bounded_end
    result.append(text[cursor:])
    return "".join(result)


def _object_value(value: Any) -> Any:
    data = stable_data(value)
    if isinstance(data, dict):
        data = dict(data)
        data.pop("relationship_id", None)
    return data


def build_responsibility_inventory(
    facts: DocumentFacts,
    contract: FillContract,
) -> ResponsibilityInventory:
    """Classify the complete shared fact surface without sampled protected regions."""

    managed_tags = managed_marker_tags(contract)
    expectations = marker_expectations(contract)
    managed_controls = tuple(
        control for control in facts.controls if control.tag in managed_tags
    )
    block_keys = {
        _paragraph_key(control.part, control.story, paragraph_index)
        for control in managed_controls
        if control.block_level
        for paragraph_index in control.paragraph_indices
    }
    inline_intervals: dict[tuple[str, str, int], list[tuple[int, int]]] = defaultdict(list)
    for control in managed_controls:
        if control.block_level:
            continue
        inline_intervals[
            _paragraph_key(control.part, control.story, control.paragraph_index)
        ].append((control.start, control.end))

    atoms: list[ResponsibilityAtom] = []
    counters: dict[str, int] = defaultdict(int)

    def add(
        base_id: str,
        owner: Owner,
        dimension: str,
        locator: str,
        value: Any,
        *,
        analyzable: bool = True,
    ) -> None:
        occurrence = counters[base_id]
        counters[base_id] += 1
        atom_id = base_id if occurrence == 0 else f"{base_id}#{occurrence}"
        atoms.append(
            ResponsibilityAtom(
                atom_id=atom_id,
                owner=owner,
                dimension=dimension,
                locator=locator,
                value=value,
                analyzable=analyzable,
            )
        )

    for paragraph in facts.paragraphs:
        key = _paragraph_key(
            paragraph.part,
            paragraph.story,
            paragraph.paragraph_index,
        )
        block_slot = key in block_keys
        owner = Owner.SLOT if block_slot else Owner.PROTECTED
        content_dimension = "slot.location_boundary" if block_slot else "protected.content"
        structure_dimension = "slot.location_boundary" if block_slot else "protected.structure"
        text = (
            paragraph.text
            if block_slot
            else _masked_text(paragraph.text, inline_intervals.get(key, []))
        )
        add(
            f"paragraph:{paragraph.path}:content",
            owner,
            content_dimension,
            paragraph.path,
            text,
        )
        add(
            f"paragraph:{paragraph.path}:structure",
            owner,
            structure_dimension,
            paragraph.path,
            {
                "story": paragraph.story,
                "part": paragraph.part,
                "paragraph_index": paragraph.paragraph_index,
                "section_index": paragraph.section_index,
                "table_index": paragraph.table_index,
                "row": paragraph.row,
                "cell": paragraph.cell,
            },
        )
        protected_run_index = 0
        slot_run_index = 0
        for run in paragraph.runs:
            in_inline_slot = any(
                _overlaps(run.start, run.end, start, end)
                for start, end in inline_intervals.get(key, [])
            )
            run_owner = Owner.SLOT if block_slot or in_inline_slot else Owner.PROTECTED
            if run_owner is Owner.SLOT:
                run_index = slot_run_index
                slot_run_index += 1
                dimension = "slot.value_style"
                prefix = "slot-run"
            else:
                run_index = protected_run_index
                protected_run_index += 1
                dimension = "protected.style"
                prefix = "protected-run"
            add(
                f"paragraph:{paragraph.path}:{prefix}[{run_index}]",
                run_owner,
                dimension,
                f"{paragraph.path}/run[{run_index}]",
                run.effective_style,
            )

    table_paragraphs: dict[tuple[str, str, int], list[tuple[str, str, int]]] = defaultdict(list)
    for paragraph in facts.paragraphs:
        if paragraph.table_index is None:
            continue
        table_paragraphs[(paragraph.part, paragraph.story, paragraph.table_index)].append(
            _paragraph_key(paragraph.part, paragraph.story, paragraph.paragraph_index)
        )
    for table in facts.tables:
        key = (table.part, table.story, table.table_index)
        paragraph_keys = table_paragraphs.get(key, [])
        slot_owned = bool(paragraph_keys) and all(item in block_keys for item in paragraph_keys)
        owner = Owner.SLOT if slot_owned else Owner.PROTECTED
        dimension = "slot.location_boundary" if slot_owned else "protected.structure"
        locator = f"{table.part}:{table.story}:table[{table.table_index}]"
        add(
            f"table:{locator}",
            owner,
            dimension,
            locator,
            {
                "row_count": table.row_count,
                "cells": [
                    {
                        "row": cell.row,
                        "cell": cell.cell,
                        "grid_span": cell.grid_span,
                        "vertical_merge": cell.vertical_merge,
                    }
                    for cell in table.cells
                ],
            },
        )

    slot_relationships: set[tuple[str, str]] = set()
    object_occurrences: dict[tuple[str, str, int | None, str], int] = defaultdict(int)
    for item in facts.objects + facts.unsupported:
        key = _paragraph_key(item.part, item.story, item.paragraph_index or 0)
        slot_owned = item.paragraph_index is not None and key in block_keys
        owner = Owner.SLOT if slot_owned else Owner.PROTECTED
        dimension = "slot.location_boundary" if slot_owned else "protected.object"
        occurrence_key = (item.part, item.story, item.paragraph_index, item.kind)
        occurrence = object_occurrences[occurrence_key]
        object_occurrences[occurrence_key] += 1
        locator = (
            f"{item.part}:{item.story}:p[{item.paragraph_index}]/"
            f"{item.kind}[{occurrence}]"
        )
        add(
            f"object:{locator}",
            owner,
            dimension,
            locator,
            _object_value(item),
            analyzable=item.status is not AssertionStatus.UNKNOWN,
        )
        if slot_owned and item.relationship_id is not None:
            slot_relationships.add((item.part, item.relationship_id))

    relationship_occurrences: dict[tuple[str, str], int] = defaultdict(int)
    for relationship in sorted(
        facts.relationships,
        key=lambda item: (
            item.source_part,
            item.relationship_type,
            item.resolved_target or item.target,
            item.relationship_id,
        ),
    ):
        owner = (
            Owner.SLOT
            if (relationship.source_part, relationship.relationship_id) in slot_relationships
            else Owner.PROTECTED
        )
        dimension = "slot.location_boundary" if owner is Owner.SLOT else "protected.object"
        group = (relationship.source_part, relationship.relationship_type)
        occurrence = relationship_occurrences[group]
        relationship_occurrences[group] += 1
        locator = (
            f"{relationship.source_part or '<package>'}:relationship:"
            f"{relationship.relationship_type}[{occurrence}]"
        )
        add(
            f"relationship:{locator}",
            owner,
            dimension,
            locator,
            {
                "relationship_type": relationship.relationship_type,
                "target": relationship.target,
                "target_mode": relationship.target_mode,
                "resolved_target": relationship.resolved_target,
                "target_exists": relationship.target_exists,
            },
        )

    for part in facts.parts:
        add(
            f"part:{part}",
            Owner.PROTECTED,
            "protected.structure",
            part,
            {"present": True},
        )

    for control in facts.controls:
        if control.tag not in managed_tags:
            locator = (
                f"{control.part}:{control.story}:p[{control.paragraph_index}]/"
                f"content-control[{control.tag or '<untagged>'}]"
            )
            add(
                f"protected-control:{locator}",
                Owner.PROTECTED,
                "protected.object",
                locator,
                {
                    "alias": control.alias,
                    "tag": control.tag,
                    "story": control.story,
                    "part": control.part,
                    "paragraph_indices": control.paragraph_indices,
                    "block_level": control.block_level,
                },
            )
            continue
        expectation = expectations[str(control.tag)]
        locator = (
            f"{control.part}:{control.story}:p[{control.paragraph_index}]/"
            f"slot[{control.tag}]"
        )
        add(
            f"slot-control:{control.tag}:inventory",
            Owner.SLOT,
            "slot.inventory",
            locator,
            {"tag": control.tag, "field_id": expectation.field_id},
        )
        add(
            f"slot-control:{control.tag}:location",
            Owner.SLOT,
            "slot.location_boundary",
            locator,
            {
                "story": control.story,
                "part": control.part,
                "paragraph_indices": control.paragraph_indices,
                "start": control.start,
                "end": control.end,
                "block_level": control.block_level,
            },
        )

    for slot in contract.slots:
        add(
            f"slot-contract:{slot.slot_id}:field",
            Owner.SLOT,
            "slot.field_mapping",
            slot.slot_id,
            {"field_id": slot.field_id, "content_type": slot.content_type},
        )
        add(
            f"slot-contract:{slot.slot_id}:style",
            Owner.SLOT,
            "slot.value_style",
            slot.slot_id,
            slot.expected_value_style,
        )

    for region in contract.regions:
        if region.owner is not Owner.REMOVE:
            continue
        add(
            f"remove-region:{region.region_id}",
            Owner.REMOVE,
            "shared.forbidden_residue",
            region.region_id,
            {
                "forbidden_text": region.forbidden_text,
                "locator": stable_data(region.locator),
            },
        )

    counts = {
        owner: sum(atom.owner is owner for atom in atoms)
        for owner in (Owner.PROTECTED, Owner.SLOT, Owner.REMOVE)
    }
    return ResponsibilityInventory(
        policy=POLICY,
        atoms=tuple(atoms),
        protected=counts[Owner.PROTECTED],
        slot=counts[Owner.SLOT],
        remove=counts[Owner.REMOVE],
        unclassified=0,
    )


def _failure_code(dimension: str) -> str | None:
    if dimension == "protected.content":
        return "required_protected_content_missing_or_changed"
    if dimension == "protected.object":
        return "required_protected_object_missing_or_broken"
    return None


def evaluate_exhaustive_protected(
    gold: ResponsibilityInventory,
    actual: ResponsibilityInventory,
    config: EvalConfig,
) -> tuple[AssertionResult, ...]:
    """Compare every protected atom in the union of Gold and Actual surfaces."""

    gold_atoms = {atom.atom_id: atom for atom in gold.atoms if atom.owner is Owner.PROTECTED}
    actual_atoms = {
        atom.atom_id: atom for atom in actual.atoms if atom.owner is Owner.PROTECTED
    }
    results: list[AssertionResult] = []
    for atom_id in sorted(set(gold_atoms) | set(actual_atoms)):
        expected = gold_atoms.get(atom_id)
        observed = actual_atoms.get(atom_id)
        reference = expected or observed
        if reference is None:
            raise AssertionError("protected atom union cannot contain an empty member")
        status = AssertionStatus.PASS
        detail = "matches"
        if expected is None:
            status = AssertionStatus.FAIL
            detail = "unexpected protected atom exists only in Actual"
        elif observed is None:
            status = AssertionStatus.FAIL
            detail = "required protected atom is missing from Actual"
        elif not expected.analyzable or not observed.analyzable:
            status = AssertionStatus.UNKNOWN
            detail = "atom is classified but its semantics are unsupported"
        elif expected.dimension == "protected.style" and isinstance(
            expected.value, EffectiveStyle
        ) and isinstance(observed.value, EffectiveStyle):
            differences = style_differences(
                expected.value,
                observed.value,
                config.tolerances,
            )
            if differences:
                status = AssertionStatus.FAIL
                detail = f"effective style differs: {differences}"
        elif stable_data(expected.value) != stable_data(observed.value):
            status = AssertionStatus.FAIL
            detail = "semantic fact differs"
        digest = hashlib.sha256(atom_id.encode("utf-8")).hexdigest()[:16]
        results.append(
            AssertionResult(
                assertion_id=f"protected.surface.{digest}",
                view=View.PROTECTED,
                dimension=reference.dimension,
                status=status,
                required=True,
                expected=None if expected is None else stable_data(expected.value),
                actual=None if observed is None else stable_data(observed.value),
                message=f"{reference.locator}: {detail}",
                failure_code=(
                    _failure_code(reference.dimension)
                    if status is AssertionStatus.FAIL
                    else None
                ),
            )
        )
    return tuple(results)


def inventory_summary(inventory: ResponsibilityInventory) -> dict[str, Any]:
    by_dimension: dict[str, int] = defaultdict(int)
    for atom in inventory.atoms:
        by_dimension[atom.dimension] += 1
    return {
        "policy": inventory.policy,
        "total_atoms": inventory.total,
        "classified_atoms": len(inventory.atoms),
        "protected_atoms": inventory.protected,
        "slot_atoms": inventory.slot,
        "remove_atoms": inventory.remove,
        "unclassified_atoms": inventory.unclassified,
        "coverage": inventory.coverage,
        "by_dimension": dict(sorted(by_dimension.items())),
    }


__all__ = [
    "POLICY",
    "build_responsibility_inventory",
    "evaluate_exhaustive_protected",
    "inventory_summary",
]
