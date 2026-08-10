"""Stable Style Contract extraction, resolution, and conformance checks."""

from docfit.styles.capture import capture_template_style_contracts
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
from docfit.styles.resolver import (
    EffectiveStyleResolver,
    EffectiveStyleResult,
    PropertyProvenance,
)
from docfit.styles.validator import (
    OccurrenceStyleValidation,
    StyleContractValidator,
    StyleDifference,
    StyleValidationReport,
)

__all__ = [
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
    "capture_template_style_contracts",
    "materialize_style_contracts",
    "style_contract_digest",
]
