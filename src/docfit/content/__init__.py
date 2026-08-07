"""Student-content extraction, placement, and deterministic template filling."""

from docfit.content.extraction import extraction_output_schema, validate_extraction
from docfit.content.placement import build_placement, load_fill_contract
from docfit.content.student import build_student_inventory

__all__ = (
    "build_placement",
    "build_student_inventory",
    "extraction_output_schema",
    "load_fill_contract",
    "validate_extraction",
)
