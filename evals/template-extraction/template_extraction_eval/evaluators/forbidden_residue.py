"""Check only Gold-declared forbidden residue; never infer removal policy."""

from __future__ import annotations

from ..models import (
    AssertionResult,
    AssertionStatus,
    DocumentFacts,
    FillContract,
    Owner,
    View,
)


def evaluate_forbidden_residue(
    gold_contract: FillContract,
    actual_facts: DocumentFacts,
) -> tuple[AssertionResult, ...]:
    assertions: list[AssertionResult] = []
    document_text = "\n".join(paragraph.text for paragraph in actual_facts.paragraphs)
    for region in gold_contract.regions:
        if region.owner is not Owner.REMOVE:
            continue
        if not region.forbidden_text:
            assertions.append(
                AssertionResult(
                    assertion_id=f"{region.region_id}.forbidden_residue",
                    view=View.SHARED,
                    dimension="shared.forbidden_residue",
                    status=AssertionStatus.UNKNOWN,
                    required=region.required,
                    region_id=region.region_id,
                    gold_locator=region.locator,
                    message="Gold remove region has no explicit forbidden_text",
                )
            )
            continue
        present = region.forbidden_text in document_text
        assertions.append(
            AssertionResult(
                assertion_id=f"{region.region_id}.forbidden_residue",
                view=View.SHARED,
                dimension="shared.forbidden_residue",
                status=AssertionStatus.FAIL if present else AssertionStatus.PASS,
                required=region.required,
                expected="absent",
                actual="present" if present else "absent",
                region_id=region.region_id,
                gold_locator=region.locator,
                message=(
                    "Gold-declared forbidden residue remains"
                    if present
                    else "Gold-declared forbidden residue is absent"
                ),
                failure_code="forbidden_residue_present" if present else None,
            )
        )
    return tuple(assertions)

