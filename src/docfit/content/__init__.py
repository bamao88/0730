"""Student-content extraction, placement, and deterministic template filling."""

from docfit.content.extraction import extraction_output_schema, validate_extraction
from docfit.content.partition import (
    BODY_FLOW_AGGREGATE_FIELD_ID,
    compile_final_content_partition,
    is_body_flow_field,
    is_generated_field,
)
from docfit.content.placement import build_placement, load_fill_contract
from docfit.content.projection import (
    TemplateStyleMap,
    TextReplacement,
    materialize_post_style_layout_closure,
    project_student_content,
    resolve_template_style_map,
)
from docfit.content.quality_patches import load_quality_patches
from docfit.content.student import build_student_inventory

__all__ = (
    "TemplateStyleMap",
    "TextReplacement",
    "BODY_FLOW_AGGREGATE_FIELD_ID",
    "build_placement",
    "build_student_inventory",
    "compile_final_content_partition",
    "extraction_output_schema",
    "is_body_flow_field",
    "is_generated_field",
    "load_fill_contract",
    "load_quality_patches",
    "materialize_post_style_layout_closure",
    "project_student_content",
    "resolve_template_style_map",
    "validate_extraction",
)
