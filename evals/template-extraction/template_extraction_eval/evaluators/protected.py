"""Evaluate protected content, structure, effective style, and objects."""

from __future__ import annotations

from typing import Any

from ..alignment import AlignmentStatus, align_region
from ..facts.effective_style import style_differences
from ..models import (
    AssertionResult,
    AssertionStatus,
    DocumentFacts,
    EvalConfig,
    FillContract,
    Owner,
    ParagraphFact,
    RegionContract,
    View,
)


def _alignment_status(status: AlignmentStatus, required: bool) -> AssertionStatus:
    if status is AlignmentStatus.AMBIGUOUS:
        return AssertionStatus.UNKNOWN
    if status is AlignmentStatus.MISSING:
        return AssertionStatus.FAIL if required else AssertionStatus.NOT_APPLICABLE
    return AssertionStatus.PASS


def _structure(paragraph: ParagraphFact) -> tuple[Any, ...]:
    return (
        paragraph.story,
        paragraph.part,
        paragraph.section_index,
        paragraph.paragraph_index,
        paragraph.table_index,
        paragraph.row,
        paragraph.cell,
    )


def _region_style(paragraph: ParagraphFact, region: RegionContract) -> Any:
    if region.text:
        start = paragraph.text.find(region.text)
        if start >= 0:
            for run in paragraph.runs:
                if run.start <= start < max(run.end, run.start + 1):
                    return run.effective_style
    return paragraph.runs[0].effective_style


def _object_value(region: RegionContract, facts: DocumentFacts) -> dict[str, Any] | None:
    candidates = [item for item in facts.objects if item.kind == region.object_kind]
    if not candidates:
        candidates = [item for item in facts.unsupported if item.kind == region.object_kind]
    if not candidates:
        return None
    item = candidates[0]
    return {
        "kind": item.kind,
        "content_sha256": item.content_sha256,
        "target": item.target,
        "status": item.status.value,
        "semantic_xml": item.semantic_xml,
    }


def evaluate_protected(
    gold_contract: FillContract,
    actual_contract: FillContract,
    gold_facts: DocumentFacts,
    actual_facts: DocumentFacts,
    eval_config: EvalConfig,
) -> tuple[AssertionResult, ...]:
    assertions: list[AssertionResult] = []
    for region in gold_contract.regions:
        if region.owner is not Owner.PROTECTED:
            continue
        if region.object_kind is not None:
            for dimension in (
                "protected.content",
                "protected.structure",
                "protected.style",
            ):
                assertions.append(
                    AssertionResult(
                        assertion_id=f"{region.region_id}.{dimension}",
                        view=View.PROTECTED,
                        dimension=dimension,
                        status=AssertionStatus.NOT_APPLICABLE,
                        required=False,
                        region_id=region.region_id,
                        gold_locator=region.locator,
                        message="object-only region has no text, structure, or style assertion",
                    )
                )
            expected_object = _object_value(region, gold_facts)
            actual_object = _object_value(region, actual_facts)
            if region.object_kind == "unsupported":
                object_status = AssertionStatus.UNKNOWN
                message = "visible altChunk semantic comparison is unsupported in v1"
            else:
                object_status = (
                    AssertionStatus.PASS
                    if actual_object is not None
                    and expected_object is not None
                    and actual_object == expected_object
                    and (
                        region.object_sha256 is None
                        or actual_object["content_sha256"] == region.object_sha256
                    )
                    else AssertionStatus.FAIL
                )
                message = (
                    "protected object matches"
                    if object_status is AssertionStatus.PASS
                    else "protected object is missing or changed"
                )
            assertions.append(
                AssertionResult(
                    assertion_id=f"{region.region_id}.object",
                    view=View.PROTECTED,
                    dimension="protected.object",
                    status=object_status,
                    required=region.required,
                    expected=expected_object,
                    actual=actual_object,
                    region_id=region.region_id,
                    gold_locator=region.locator,
                    message=message,
                    failure_code=(
                        "required_protected_object_missing_or_broken"
                        if object_status is AssertionStatus.FAIL
                        else None
                    ),
                )
            )
            continue
        alignment = align_region(region, actual_contract, gold_facts, actual_facts)
        base_status = _alignment_status(alignment.status, region.required)
        if base_status is not AssertionStatus.PASS:
            for dimension in (
                "protected.content",
                "protected.structure",
                "protected.style",
                "protected.object",
            ):
                status = base_status
                if dimension == "protected.object" and region.object_kind is None:
                    status = AssertionStatus.NOT_APPLICABLE
                assertions.append(
                    AssertionResult(
                        assertion_id=f"{region.region_id}.{dimension}",
                        view=View.PROTECTED,
                        dimension=dimension,
                        status=status,
                        required=region.required,
                        region_id=region.region_id,
                        gold_locator=region.locator,
                        actual_locator=(
                            None
                            if alignment.actual_region is None
                            else alignment.actual_region.locator
                        ),
                        message=alignment.detail or "protected region cannot be aligned",
                        failure_code=(
                            "required_protected_content_missing_or_changed"
                            if status is AssertionStatus.FAIL
                            else None
                        ),
                    )
                )
            continue
        if alignment.gold_paragraph is None or alignment.actual_paragraph is None:
            raise AssertionError("matched region alignment must include both paragraphs")
        actual_region = alignment.actual_region
        if actual_region is None:
            raise AssertionError("matched region alignment must include Actual contract region")

        expected_text = region.text
        actual_text = actual_region.text
        content_status = AssertionStatus.NOT_APPLICABLE
        if expected_text is not None:
            content_status = (
                AssertionStatus.PASS
                if actual_text == expected_text and actual_text in alignment.actual_paragraph.text
                else AssertionStatus.FAIL
            )
        assertions.append(
            AssertionResult(
                assertion_id=f"{region.region_id}.content",
                view=View.PROTECTED,
                dimension="protected.content",
                status=content_status,
                required=region.required,
                expected=expected_text,
                actual=actual_text,
                region_id=region.region_id,
                gold_locator=region.locator,
                actual_locator=actual_region.locator,
                message=(
                    "protected text matches"
                    if content_status is AssertionStatus.PASS
                    else "protected text changed"
                ),
                failure_code=(
                    "required_protected_content_missing_or_changed"
                    if content_status is AssertionStatus.FAIL
                    else None
                ),
            )
        )

        expected_structure = _structure(alignment.gold_paragraph)
        actual_structure = _structure(alignment.actual_paragraph)
        structure_status = (
            AssertionStatus.PASS
            if expected_structure == actual_structure
            else AssertionStatus.FAIL
        )
        assertions.append(
            AssertionResult(
                assertion_id=f"{region.region_id}.structure",
                view=View.PROTECTED,
                dimension="protected.structure",
                status=structure_status,
                required=region.required,
                expected=expected_structure,
                actual=actual_structure,
                region_id=region.region_id,
                gold_locator=region.locator,
                actual_locator=actual_region.locator,
                message=(
                    "protected structure matches"
                    if structure_status is AssertionStatus.PASS
                    else "protected structure moved"
                ),
                failure_code=(
                    "wrong_structural_location"
                    if structure_status is AssertionStatus.FAIL
                    else None
                ),
            )
        )

        gold_style = _region_style(alignment.gold_paragraph, region)
        actual_style = _region_style(alignment.actual_paragraph, actual_region)
        differences = style_differences(gold_style, actual_style, eval_config.tolerances)
        style_status = AssertionStatus.PASS if not differences else AssertionStatus.FAIL
        assertions.append(
            AssertionResult(
                assertion_id=f"{region.region_id}.style",
                view=View.PROTECTED,
                dimension="protected.style",
                status=style_status,
                required=region.required,
                expected=gold_style,
                actual=actual_style,
                region_id=region.region_id,
                gold_locator=region.locator,
                actual_locator=actual_region.locator,
                message=(
                    "protected style matches"
                    if not differences
                    else f"protected style differs: {differences}"
                ),
            )
        )

        assertions.append(
            AssertionResult(
                assertion_id=f"{region.region_id}.object",
                view=View.PROTECTED,
                dimension="protected.object",
                status=AssertionStatus.NOT_APPLICABLE,
                required=False,
                region_id=region.region_id,
                gold_locator=region.locator,
                actual_locator=actual_region.locator,
                message="text-only protected region has no object assertion",
            )
        )
    return tuple(assertions)
