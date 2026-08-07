"""Public schema for template_compare."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_COMPARE_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "schema_version": {"const": 1},
        "task_root": {"type": "string", "minLength": 1},
        "action": {"const": "create"},
        "review_mode": {
            "type": "string",
            "enum": ["mutation_review", "final_review"],
        },
        "before_snapshot_ref": {"type": "string"},
        "after_snapshot_ref": {"type": "string"},
        "mutation_ref": {"type": "string"},
        "final_snapshot_ref": {"type": "string"},
        "render_ref": {"type": "string", "pattern": "^render:v2:[0-9a-f]{64}$"},
        "reviewed_pages": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "integer", "minimum": 1},
        },
        "evidence_refs": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "pattern": "^visual:v2:[0-9a-f]{64}$"},
        },
        "findings": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["schema_version", "task_root", "action"],
    "additionalProperties": False,
}
