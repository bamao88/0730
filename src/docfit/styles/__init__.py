"""Stable Style Contract extraction, resolution, and conformance checks."""

from docfit.styles.actual_roles import ActualRoleSource, ActualStyleRole, ActualStyleRoleSet
from docfit.styles.capture import (
    SchoolStyleCapture,
    capture_template_style_contracts,
    capture_template_style_observations,
    compile_school_style_contracts,
)
from docfit.styles.contracts import (
    STYLE_CONTRACT_SCHEMA_VERSION,
    OverridePolicy,
    StyleContract,
    StyleContractRef,
    StyleContractSet,
    style_contract_digest,
)
from docfit.styles.materialization import (
    SUPPORTED_MATERIALIZED_PROPERTIES,
    materialize_style_contracts,
)
from docfit.styles.observation import (
    EffectiveState,
    FieldStyleObservation,
    FieldStyleObservationSet,
    ObservationClosure,
    ObservationClosureSummary,
    PropertyObservation,
    SchoolEvidenceStatus,
    SchoolRoleEligibility,
    observe_effective_style,
)
from docfit.styles.preflight import (
    TaskLocalStyleTarget,
    compile_task_local_style_target,
)
from docfit.styles.presets import (
    FieldStyleBinding,
    GeneralStylePreset,
    PresetProperty,
    PresetRole,
)
from docfit.styles.profiles import (
    DEFAULT_STYLE_PROPERTY_PROFILES,
    DOCUMENT_ROLE_PROPERTY_PATHS,
    PROFILE_REGISTRY_SCHEMA_VERSION,
    PROFILE_SCHEMA_VERSION,
    STYLE_ROLE_PROPERTY_PATHS,
    PropertyDefinition,
    StylePropertyProfile,
    StylePropertyProfileRef,
    StylePropertyProfileRegistry,
)
from docfit.styles.resolver import (
    EffectiveStyleResolver,
    EffectiveStyleResult,
    PropertyProvenance,
)
from docfit.styles.selection import (
    SelectedStyleProperty,
    SelectedStyleRole,
    StyleRoleSelectionReceipt,
    compile_selected_style_contracts,
    select_complete_style_roles,
)
from docfit.styles.validator import (
    OccurrenceStyleValidation,
    StyleContractValidator,
    StyleDifference,
    StyleValidationReport,
)

__all__ = [
    "ActualRoleSource",
    "ActualStyleRole",
    "ActualStyleRoleSet",
    "STYLE_CONTRACT_SCHEMA_VERSION",
    "OverridePolicy",
    "StyleContract",
    "StyleContractRef",
    "StyleContractSet",
    "EffectiveStyleResolver",
    "EffectiveStyleResult",
    "PropertyProvenance",
    "StyleContractValidator",
    "StyleDifference",
    "OccurrenceStyleValidation",
    "StyleValidationReport",
    "SUPPORTED_MATERIALIZED_PROPERTIES",
    "DEFAULT_STYLE_PROPERTY_PROFILES",
    "DOCUMENT_ROLE_PROPERTY_PATHS",
    "EffectiveState",
    "FieldStyleObservation",
    "FieldStyleObservationSet",
    "FieldStyleBinding",
    "GeneralStylePreset",
    "ObservationClosure",
    "ObservationClosureSummary",
    "PROFILE_REGISTRY_SCHEMA_VERSION",
    "PROFILE_SCHEMA_VERSION",
    "PropertyDefinition",
    "PropertyObservation",
    "PresetProperty",
    "PresetRole",
    "STYLE_ROLE_PROPERTY_PATHS",
    "SchoolEvidenceStatus",
    "SchoolRoleEligibility",
    "SchoolStyleCapture",
    "SelectedStyleProperty",
    "SelectedStyleRole",
    "StylePropertyProfile",
    "StylePropertyProfileRef",
    "StylePropertyProfileRegistry",
    "StyleRoleSelectionReceipt",
    "TaskLocalStyleTarget",
    "capture_template_style_observations",
    "capture_template_style_contracts",
    "compile_selected_style_contracts",
    "compile_task_local_style_target",
    "compile_school_style_contracts",
    "materialize_style_contracts",
    "observe_effective_style",
    "select_complete_style_roles",
    "style_contract_digest",
]
