"""Shadow materialization plan assembly."""

from __future__ import annotations

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.compiler import compile_materialization_intents
from docfit.template.materialization.context import resolve_materialization_contexts
from docfit.template.materialization.models import (
    MaterializationCompileResult,
    MaterializationPlan,
)
from docfit.template.materialization.validators import validate_materialization_plan
from docfit.tools.runtime import JsonObject


def build_shadow_materialization_plan(
    *,
    inventory: JsonObject,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> MaterializationCompileResult:
    compiled = compile_materialization_intents(review=review, registry=registry)
    context_resolution = resolve_materialization_contexts(
        inventory=inventory,
        intents=compiled.intents,
    )
    plan = MaterializationPlan(
        plan_ref=compiled.plan.plan_ref,
        intents=compiled.plan.intents,
        contexts=context_resolution.contexts,
        commands=compiled.plan.commands,
        unsupported=(
            *compiled.plan.unsupported,
            *context_resolution.unsupported,
        ),
        source_review_digest=compiled.plan.source_review_digest,
    )
    validation_unsupported = validate_materialization_plan(plan=plan)
    if validation_unsupported:
        plan = MaterializationPlan(
            plan_ref=plan.plan_ref,
            intents=plan.intents,
            contexts=plan.contexts,
            commands=plan.commands,
            unsupported=(*plan.unsupported, *validation_unsupported),
            source_review_digest=plan.source_review_digest,
        )
    return MaterializationCompileResult(plan=plan)
