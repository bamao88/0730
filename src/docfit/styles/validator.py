"""Occurrence-level Style Contract validation for final DOCX output."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from docfit.styles.contracts import StyleContractSet
from docfit.styles.resolver import EffectiveStyleResolver, PropertyProvenance
from docfit.tools.runtime import JsonObject, ToolFailure

ValidationStatus = Literal["passed", "failed", "unresolved"]


@dataclass(frozen=True, slots=True)
class StyleDifference:
    property_path: str
    expected: str | float | bool | None
    actual: str | float | bool | None
    provenance: tuple[PropertyProvenance, ...]

    def as_dict(self) -> JsonObject:
        return {
            "property_path": self.property_path,
            "expected": self.expected,
            "actual": self.actual,
            "provenance": [item.as_dict() for item in self.provenance],
        }


@dataclass(frozen=True, slots=True)
class OccurrenceStyleValidation:
    occurrence_id: str
    style_contract_id: str
    contract_digest: str
    locator: str | Mapping[str, Any]
    status: ValidationStatus
    differences: tuple[StyleDifference, ...]
    unresolved_properties: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> JsonObject:
        locator: Any = dict(self.locator) if isinstance(self.locator, Mapping) else self.locator
        return {
            "occurrence_id": self.occurrence_id,
            "style_contract_id": self.style_contract_id,
            "contract_digest": self.contract_digest,
            "locator": locator,
            "status": self.status,
            "differences": [item.as_dict() for item in self.differences],
            "unresolved_properties": list(self.unresolved_properties),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class StyleValidationReport:
    results: tuple[OccurrenceStyleValidation, ...]

    @property
    def passed(self) -> tuple[OccurrenceStyleValidation, ...]:
        return tuple(item for item in self.results if item.status == "passed")

    @property
    def failed(self) -> tuple[OccurrenceStyleValidation, ...]:
        return tuple(item for item in self.results if item.status == "failed")

    @property
    def unresolved(self) -> tuple[OccurrenceStyleValidation, ...]:
        return tuple(item for item in self.results if item.status == "unresolved")

    @property
    def status(self) -> ValidationStatus:
        if self.failed:
            return "failed"
        if self.unresolved:
            return "unresolved"
        return "passed"

    def as_dict(self) -> JsonObject:
        return {
            "status": self.status,
            "counts": {
                "passed": len(self.passed),
                "failed": len(self.failed),
                "unresolved": len(self.unresolved),
            },
            "passed": [item.as_dict() for item in self.passed],
            "failed": [item.as_dict() for item in self.failed],
            "unresolved": [item.as_dict() for item in self.unresolved],
        }


class StyleContractValidator:
    """Re-resolve and compare every managed property in an occurrence manifest."""

    def __init__(self, contracts: StyleContractSet) -> None:
        self.contracts = contracts

    def validate(
        self,
        document: Path,
        occurrence_manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    ) -> StyleValidationReport:
        raw_occurrences: object
        if isinstance(occurrence_manifest, Mapping):
            raw_occurrences = occurrence_manifest.get("occurrences")
        else:
            raw_occurrences = occurrence_manifest
        if not isinstance(raw_occurrences, Sequence) or isinstance(
            raw_occurrences, str | bytes
        ):
            raise _manifest_failure("Occurrence manifest requires an occurrences array.")
        resolver = EffectiveStyleResolver(document)
        results: list[OccurrenceStyleValidation] = []
        for index, raw in enumerate(raw_occurrences, start=1):
            if not isinstance(raw, Mapping):
                raise _manifest_failure("Every occurrence must be an object.")
            results.append(self._validate_occurrence(resolver, raw, index=index))
        return StyleValidationReport(tuple(results))

    def _validate_occurrence(
        self,
        resolver: EffectiveStyleResolver,
        occurrence: Mapping[str, Any],
        *,
        index: int,
    ) -> OccurrenceStyleValidation:
        occurrence_id = occurrence.get("occurrence_id", f"occurrence-{index}")
        locator = occurrence.get("locator")
        style_ref = occurrence.get("style_contract_ref")
        if not isinstance(occurrence_id, str) or not occurrence_id:
            raise _manifest_failure("occurrence_id must be a non-empty string.")
        if not isinstance(locator, str | Mapping):
            raise _manifest_failure(f"{occurrence_id} requires a locator.")
        if not isinstance(style_ref, Mapping):
            raise _manifest_failure(f"{occurrence_id} requires style_contract_ref.")
        try:
            contract = self.contracts.resolve(style_ref)
        except ToolFailure as error:
            return OccurrenceStyleValidation(
                occurrence_id=occurrence_id,
                style_contract_id=str(style_ref.get("style_contract_id", "")),
                contract_digest=str(style_ref.get("contract_digest", "")),
                locator=locator,
                status="unresolved",
                differences=(),
                unresolved_properties=(),
                reasons=(error.message,),
            )
        try:
            actual = resolver.resolve(locator)
        except ToolFailure as error:
            return OccurrenceStyleValidation(
                occurrence_id=occurrence_id,
                style_contract_id=contract.style_contract_id,
                contract_digest=contract.contract_digest,
                locator=locator,
                status="unresolved",
                differences=(),
                unresolved_properties=contract.owned_properties,
                reasons=(error.message,),
            )

        differences: list[StyleDifference] = []
        unresolved_properties: list[str] = []
        for property_path in contract.owned_properties:
            if property_path not in actual.coverage:
                unresolved_properties.append(property_path)
                continue
            expected = contract.effective_properties[property_path]
            observed = actual.properties[property_path]
            if not _equal(expected, observed):
                differences.append(
                    StyleDifference(
                        property_path=property_path,
                        expected=expected,
                        actual=observed,
                        provenance=actual.provenance.get(property_path, ()),
                    )
                )
        reasons = list(actual.unresolved)
        if differences:
            status: ValidationStatus = "failed"
        elif unresolved_properties or reasons:
            status = "unresolved"
        else:
            status = "passed"
        return OccurrenceStyleValidation(
            occurrence_id=occurrence_id,
            style_contract_id=contract.style_contract_id,
            contract_digest=contract.contract_digest,
            locator=locator,
            status=status,
            differences=tuple(differences),
            unresolved_properties=tuple(unresolved_properties),
            reasons=tuple(reasons),
        )


def _equal(expected: object, actual: object) -> bool:
    if (
        isinstance(expected, int | float)
        and not isinstance(expected, bool)
        and isinstance(actual, int | float)
        and not isinstance(actual, bool)
    ):
        return math.isclose(float(expected), float(actual), rel_tol=0.0, abs_tol=1e-9)
    return expected == actual


def _manifest_failure(message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code="style_occurrence_manifest_invalid",
        message=message,
        suggested_actions=("repair_occurrence_manifest",),
    )
