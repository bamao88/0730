"""Shared immutable models for the independent template-extraction Eval."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast


class AssertionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Owner(StrEnum):
    PROTECTED = "protected"
    SLOT = "slot"
    REMOVE = "remove"


class Dimension(StrEnum):
    PROTECTED_CONTENT = "protected.content"
    PROTECTED_STRUCTURE = "protected.structure"
    PROTECTED_STYLE = "protected.style"
    PROTECTED_OBJECT = "protected.object"
    SLOT_INVENTORY = "slot.inventory"
    SLOT_LOCATION_BOUNDARY = "slot.location_boundary"
    SLOT_FIELD_MAPPING = "slot.field_mapping"
    SLOT_VALUE_STYLE = "slot.value_style"
    SHARED_FORBIDDEN_RESIDUE = "shared.forbidden_residue"
    SHARED_INPUT_INTEGRITY = "shared.input_integrity"
    SHARED_ANALYSIS_COVERAGE = "shared.analysis_coverage"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class View(StrEnum):
    PROTECTED = "protected"
    SLOT = "slot"
    SHARED = "shared"


@dataclass(frozen=True)
class Locator:
    type: str
    story: str
    part: str
    expected_match_count: int
    value: str | None = None
    section_index: int | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    row: int | None = None
    cell: int | None = None
    left_anchor: str | None = None
    right_anchor: str | None = None
    occurrence: int | None = None
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class EffectiveStyle:
    font: dict[str, Any]
    paragraph: dict[str, Any]
    container: dict[str, Any]
    page: dict[str, Any]


@dataclass(frozen=True)
class RegionContract:
    region_id: str
    owner: Owner
    required: bool
    locator: Locator | None
    start_locator: Locator | None = None
    end_locator: Locator | None = None
    field_ids: tuple[str, ...] = ()
    placement_mode: str | None = None
    text: str | None = None
    forbidden_text: str | None = None
    object_kind: str | None = None
    object_sha256: str | None = None
    expected_style: EffectiveStyle | None = None


@dataclass(frozen=True)
class ComponentLocator:
    locator: Locator
    role: str | None = None


@dataclass(frozen=True)
class SlotContract:
    slot_id: str
    field_id: str
    content_type: str
    required: bool
    locator: Locator
    expected_value_style: EffectiveStyle
    cardinality: str = "one"
    component_locators: tuple[ComponentLocator, ...] = ()


@dataclass(frozen=True)
class FillContract:
    schema_version: str
    contract_id: str
    template_sha256: str
    registry_id: str
    registry_version: str
    registry_sha256: str
    marker_protocol: str
    regions: tuple[RegionContract, ...]
    slots: tuple[SlotContract, ...]
    status: str | None = None


@dataclass(frozen=True)
class RegistryField:
    field_id: str
    label: str
    meaning: str
    content_type: str
    cardinality: str
    parent_field_id: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class FieldRegistry:
    schema_version: str
    registry_id: str
    registry_version: str
    status: str
    open_world: bool
    fields: tuple[RegistryField, ...]
    sha256: str

    @property
    def by_id(self) -> dict[str, RegistryField]:
        return {field.field_id: field for field in self.fields}


@dataclass(frozen=True)
class FileReference:
    path: Path
    id: str
    version: str
    sha256: str


@dataclass(frozen=True)
class CaseDefinition:
    schema_version: str
    case_id: str
    case_path: Path
    gold_template_path: Path
    gold_contract_path: Path
    registry_ref: FileReference
    eval_config_ref: FileReference
    scoring_version: str
    expected_verdict: str | None = None
    case_status: str | None = None
    gold_review_status: str | None = None


@dataclass(frozen=True)
class EvalConfig:
    schema_version: str
    config_id: str
    marker_protocol: str
    field_identity_property: str
    slot_identity_property: str
    internal_id_property: str
    tolerances: dict[str, float]
    normalization: tuple[str, ...]
    scoring_path: Path
    scoring_version: str
    scoring_sha256: str
    sha256: str


@dataclass(frozen=True)
class ScoringConfig:
    schema_version: str
    scoring_version: str
    total_points: float
    weights: dict[str, float]
    hard_failures: tuple[str, ...]
    sha256: str


@dataclass(frozen=True)
class EvalInputs:
    case: CaseDefinition
    actual_template_path: Path
    actual_contract_path: Path
    actual_contract: FillContract
    gold_contract: FillContract
    field_registry: FieldRegistry
    eval_config: EvalConfig
    scoring_config: ScoringConfig
    input_hashes: dict[str, str]


@dataclass(frozen=True)
class RelationshipFact:
    source_part: str
    relationship_id: str
    relationship_type: str
    target: str
    target_mode: str
    resolved_target: str | None
    target_exists: bool | None


@dataclass(frozen=True)
class RunFact:
    text: str
    start: int
    end: int
    style_id: str | None
    effective_style: EffectiveStyle


@dataclass(frozen=True)
class ParagraphFact:
    story: str
    part: str
    paragraph_index: int
    section_index: int
    path: str
    text: str
    tokens: tuple[str, ...]
    runs: tuple[RunFact, ...]
    table_index: int | None = None
    row: int | None = None
    cell: int | None = None


@dataclass(frozen=True)
class ContentControlFact:
    alias: str | None
    tag: str | None
    internal_id: str | None
    story: str
    part: str
    paragraph_index: int
    start: int
    end: int
    text: str
    effective_style: EffectiveStyle


@dataclass(frozen=True)
class CellFact:
    row: int
    cell: int
    text: str
    grid_span: int
    vertical_merge: str | None


@dataclass(frozen=True)
class TableFact:
    story: str
    part: str
    table_index: int
    row_count: int
    cells: tuple[CellFact, ...]


@dataclass(frozen=True)
class ObjectFact:
    kind: str
    story: str
    part: str
    paragraph_index: int | None
    relationship_id: str | None = None
    target: str | None = None
    content_sha256: str | None = None
    width_emu: int | None = None
    height_emu: int | None = None
    semantic_xml: str | None = None
    name: str | None = None
    value: str | None = None
    status: AssertionStatus = AssertionStatus.PASS
    detail: str | None = None


@dataclass(frozen=True)
class DocumentFacts:
    document_sha256: str
    parts: tuple[str, ...]
    relationships: tuple[RelationshipFact, ...]
    paragraphs: tuple[ParagraphFact, ...]
    controls: tuple[ContentControlFact, ...]
    tables: tuple[TableFact, ...]
    objects: tuple[ObjectFact, ...]
    unsupported: tuple[ObjectFact, ...]

    @property
    def controls_by_tag(self) -> dict[str, ContentControlFact]:
        return {control.tag: control for control in self.controls if control.tag is not None}


@dataclass(frozen=True)
class AssertionResult:
    assertion_id: str
    view: View
    dimension: str
    status: AssertionStatus
    required: bool
    expected: Any = None
    actual: Any = None
    region_id: str | None = None
    slot_id: str | None = None
    gold_locator: Locator | None = None
    actual_locator: Locator | None = None
    message: str = ""
    failure_code: str | None = None


@dataclass(frozen=True)
class Issue:
    issue_id: str
    severity: Severity
    view: View
    dimension: str
    assertion_id: str
    status: AssertionStatus
    message: str
    region_id: str | None = None
    slot_id: str | None = None
    gold_locator: Locator | None = None
    actual_locator: Locator | None = None
    expected: Any = None
    actual: Any = None


@dataclass(frozen=True)
class DimensionScore:
    dimension: str
    weight: float
    score: float
    passed: int
    failed: int
    unknown: int
    not_applicable: int


@dataclass(frozen=True)
class ViewScore:
    view: View
    weight: float
    score: float


@dataclass(frozen=True)
class EvalReport:
    schema_version: str
    case_id: str
    run_id: str
    status: Verdict
    total_score: float
    provisional: bool
    analysis_coverage: float
    views: tuple[ViewScore, ...]
    dimensions: tuple[DimensionScore, ...]
    issues: tuple[Issue, ...]
    inputs: dict[str, str]
    config: dict[str, Any]


def stable_data(value: Any) -> Any:
    """Convert models into stable JSON-compatible data without hidden I/O."""

    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: stable_data(getattr(value, field.name))
            for field in fields(cast(Any, value))
        }
    if isinstance(value, dict):
        return {
            str(key): stable_data(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [stable_data(item) for item in value]
    return value
