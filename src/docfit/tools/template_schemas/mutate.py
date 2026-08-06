"""Public schema for template_mutate."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_MUTATE_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "schema_version": {"const": 1},
        "task_root": {"type": "string", "minLength": 1},
        "mutation_plan_path": {"type": "string", "minLength": 1},
        "output_docx": {"type": "string", "minLength": 1},
    },
    "required": ["schema_version", "task_root", "mutation_plan_path", "output_docx"],
    "additionalProperties": False,
}
