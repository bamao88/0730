"""Student-content extraction, placement, and deterministic template filling."""

from docfit.content.extraction import extraction_output_schema, validate_extraction
from docfit.content.placement import build_placement, load_fill_contract
from docfit.content.projection import (
    TemplateStyleMap,
    TextReplacement,
    project_student_content,
    resolve_template_style_map,
)
from docfit.content.quality_patches import load_quality_patches
from docfit.content.student import build_student_inventory

__all__ = (
    "TemplateStyleMap",
    "TextReplacement",
    "build_placement",
    "build_student_inventory",
    "extraction_output_schema",
    "load_fill_contract",
    "load_quality_patches",
    "project_student_content",
    "resolve_template_style_map",
    "validate_extraction",
)
