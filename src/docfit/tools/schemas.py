"""Versioned JSON Schemas for the five stable Agent-visible Tools."""

from __future__ import annotations

from typing import Any

JsonSchema = dict[str, Any]

OBJECT_REF_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "document_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "object_id": {"type": "string", "pattern": "^obj-[0-9a-f]{24}$"},
        "expected_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "required": [
        "document_sha256",
        "object_id",
        "expected_fingerprint",
    ],
    "additionalProperties": False,
}

_TASK_ROOT: JsonSchema = {
    "type": "string",
    "description": "Authorized task root; defaults to DOCFIT_TASK_ROOT or the process cwd.",
}

INSPECT_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "task_root": _TASK_ROOT,
        "input_docx": {"type": "string"},
        "focus": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "structure",
                    "styles",
                    "visible_objects",
                    "template_rules",
                    "thesis_content",
                ],
            },
            "uniqueItems": True,
        },
        "output": {"type": "string"},
    },
    "required": ["input_docx"],
    "additionalProperties": False,
}

_EDIT_OPERATION_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "replace_text",
                "apply_style",
                "set_properties",
                "import_content_objects",
                "clear_content",
                "remove_object",
                "materialize_slot",
                "materialize_structure",
                "normalize_effective_format",
                "refresh_toc",
                "ensure_page_start",
            ],
        },
        "target_ref": OBJECT_REF_SCHEMA,
        "expected_text": {"type": "string", "minLength": 1},
        "replacement": {"type": "string"},
        "style": {"type": "string", "minLength": 1},
        "properties": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": ["string", "number", "boolean"]},
        },
        "source_docx": {"type": "string"},
        "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "source_refs": {
            "type": "array",
            "items": OBJECT_REF_SCHEMA,
            "minItems": 1,
        },
        "target_anchor_ref": OBJECT_REF_SCHEMA,
        "position": {"type": "string", "enum": ["before", "after", "end"]},
        "include_source_final_section_properties": {"type": "boolean"},
        "field_id": {"type": "string", "minLength": 1},
        "slot_id": {"type": "string", "minLength": 1},
        "placeholder_text": {"type": "string", "minLength": 1},
        "effective_format": {
            "type": "object",
            "properties": {
                "color": {"const": "black"},
                "underline": {"const": "none"},
            },
            "additionalProperties": False,
        },
        "members": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_ref": OBJECT_REF_SCHEMA,
                    "field_id": {"type": "string", "minLength": 1},
                    "slot_id": {"type": "string", "minLength": 1},
                    "placeholder_text": {"type": "string", "minLength": 1},
                    "effective_format": {
                        "type": "object",
                        "properties": {
                            "color": {"const": "black"},
                            "underline": {"const": "none"},
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["target_ref", "field_id"],
                "additionalProperties": False,
            },
            "minItems": 1,
        },
        "replaced_structure_ref": OBJECT_REF_SCHEMA,
        "toc_entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_ref": OBJECT_REF_SCHEMA,
                    "level": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["target_ref", "level"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 64,
        },
        "mode": {"type": "string", "enum": ["new_page"]},
    },
    # The runtime validates the action-specific required fields. Keeping one
    # flat schema avoids composition keywords that the supported compatible
    # backends turn into literal Tool arguments.
    "required": ["action"],
    "additionalProperties": False,
}

EDIT_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "task_root": _TASK_ROOT,
        "input_docx": {"type": "string"},
        "output_docx": {"type": "string"},
        "field_registry": {"type": "string"},
        "operations": {
            "type": "array",
            "items": _EDIT_OPERATION_SCHEMA,
            "minItems": 1,
        },
        "overwrite": {"type": "boolean"},
    },
    "required": ["input_docx", "output_docx", "operations"],
    "additionalProperties": False,
}

RENDER_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "input_docx": {"type": "string"},
        "overview": {"type": "boolean"},
    },
    "required": ["input_docx"],
    "additionalProperties": False,
}

VISUAL_REVIEW_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "render_ref": {"type": "string", "pattern": "^render:v2:[0-9a-f]{64}$"},
        "mode": {
            "type": "string",
            "enum": ["contact_sheet", "pages", "regions", "compare"],
        },
        "quality": {
            "type": "string",
            "enum": ["thumbnail", "review", "detail"],
        },
        "pages": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "uniqueItems": True,
        },
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "enum": ["object_ref", "text", "image_bbox"],
                    },
                    "object_ref": OBJECT_REF_SCHEMA,
                    "text": {"type": "string", "minLength": 1},
                    "occurrence": {"type": "integer", "minimum": 1},
                    "evidence_ref": {
                        "type": "string",
                        "pattern": "^visual:v2:[0-9a-f]{64}$",
                    },
                    "bbox_px": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "padding": {"type": "integer", "minimum": 0, "maximum": 256},
                },
                "required": ["selector"],
                "additionalProperties": False,
            },
        },
        "compare_render_ref": {
            "type": "string",
            "pattern": "^render:v2:[0-9a-f]{64}$",
        },
        "cursor": {"type": "string"},
    },
    # A single flat object is intentional: the supported Anthropic-compatible
    # backends interpret top-level oneOf as a literal argument. Real review
    # Mode-specific fields remain runtime-validated because compatible
    # backends interpret top-level oneOf as a literal Tool argument.
    "required": ["render_ref", "mode"],
    "additionalProperties": False,
}

VALIDATE_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "task_root": _TASK_ROOT,
        "source_docx": {"type": "string"},
        "final_docx": {"type": "string"},
        "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "knowledge_version": {"type": "string"},
        "task_rule_evidence": {"type": "array", "items": {"type": "object"}},
        "visual_review": {
            "type": ["string", "object"],
            "description": (
                "A task-local JSON path or the Agent's structured final visual-review evidence."
            ),
        },
        "candidate_render_ref": {"type": "string"},
        "required_visual_coverage": {"const": "all_final_pages"},
    },
    "required": ["source_docx", "final_docx"],
    "additionalProperties": False,
}
