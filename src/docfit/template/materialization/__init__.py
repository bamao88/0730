"""Post-unit template materialization planning boundaries."""

from docfit.template.materialization.compiler import compile_materialization_intents
from docfit.template.materialization.context import resolve_materialization_contexts
from docfit.template.materialization.executor import write_materialized_docx
from docfit.template.materialization.field_binding import (
    explicit_materialization_field_ids,
)
from docfit.template.materialization.handlers.body_structure import materialize_body_structure
from docfit.template.materialization.handlers.cleanup import (
    is_delete_treatment,
    should_remove_paragraph,
)
from docfit.template.materialization.handlers.fixed_content import apply_fixed_content_cleanup
from docfit.template.materialization.handlers.generated_content import (
    generated_content_policy_receipts,
)
from docfit.template.materialization.handlers.slots import materialize_slot_paragraph
from docfit.template.materialization.handlers.table_manual_cells import (
    manual_table_cell_policy_receipts,
)
from docfit.template.materialization.instruction_notes import (
    is_instruction_parenthetical,
    strip_instruction_parentheticals,
)
from docfit.template.materialization.layout_placeholders import (
    normalize_square_placeholders,
)
from docfit.template.materialization.models import (
    MaterializationCompileResult,
    MaterializationContext,
    MaterializationContextKind,
    MaterializationContextResolution,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
    MaterializationReceipt,
    MutationCommand,
    MutationCommandType,
    ScopeRef,
    UnsupportedMaterialization,
)
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.readiness import (
    is_materializable_judgment,
    materialization_readiness_feedback,
)
from docfit.template.materialization.receipts import build_materialization_receipts
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.materialization.validators import validate_materialization_plan

__all__ = [
    "MaterializationCompileResult",
    "MaterializationContext",
    "MaterializationContextKind",
    "MaterializationContextResolution",
    "MaterializationIntent",
    "MaterializationIntentType",
    "MaterializationPlan",
    "MaterializationReceipt",
    "MutationCommand",
    "MutationCommandType",
    "ScopeRef",
    "UnsupportedMaterialization",
    "build_materialization_receipts",
    "build_shadow_materialization_plan",
    "compile_materialization_intents",
    "explicit_materialization_field_ids",
    "is_materializable_judgment",
    "apply_fixed_content_cleanup",
    "is_delete_treatment",
    "is_instruction_parenthetical",
    "generated_content_policy_receipts",
    "manual_table_cell_policy_receipts",
    "materialization_readiness_feedback",
    "materialize_template_from_semantics",
    "materialize_body_structure",
    "materialize_slot_paragraph",
    "normalize_square_placeholders",
    "resolve_materialization_contexts",
    "should_remove_paragraph",
    "strip_instruction_parentheticals",
    "validate_materialization_plan",
    "write_materialized_docx",
]
