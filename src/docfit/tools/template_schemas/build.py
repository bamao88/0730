"""Public schema for template_build."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_BUILD_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "schema_version": {"const": 1},
        "task_root": {"type": "string", "minLength": 1},
        "final_snapshot_ref": {"type": "string", "minLength": 1},
        "artifact_spec_path": {"type": "string", "minLength": 1},
        "output_dir": {"const": "output/template-artifact"},
    },
    "required": [
        "schema_version",
        "task_root",
        "final_snapshot_ref",
        "artifact_spec_path",
        "output_dir",
    ],
    "additionalProperties": False,
}
