"""Business evaluators consume shared facts; they do not read DOCX packages."""

from .forbidden_residue import evaluate_forbidden_residue
from .protected import evaluate_protected
from .slots import evaluate_slots

__all__ = ["evaluate_forbidden_residue", "evaluate_protected", "evaluate_slots"]

