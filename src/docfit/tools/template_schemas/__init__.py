"""JSON schemas for the template extraction Tool set."""

from docfit.tools.template_schemas.build import TEMPLATE_BUILD_SCHEMA
from docfit.tools.template_schemas.compare import TEMPLATE_COMPARE_SCHEMA
from docfit.tools.template_schemas.mutate import TEMPLATE_MUTATE_SCHEMA
from docfit.tools.template_schemas.observe import TEMPLATE_OBSERVE_SCHEMA

__all__ = [
    "TEMPLATE_BUILD_SCHEMA",
    "TEMPLATE_COMPARE_SCHEMA",
    "TEMPLATE_MUTATE_SCHEMA",
    "TEMPLATE_OBSERVE_SCHEMA",
]
