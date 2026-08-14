"""Offline DocFit evaluation entry points."""

from docfit.evals.runner import CoreEvalReport, run_core_eval
from docfit.evals.student_content import (
    StudentContentEvalInputError,
    StudentContentEvalResult,
    compare_student_content,
    run_student_content_eval,
)

__all__ = [
    "CoreEvalReport",
    "StudentContentEvalInputError",
    "StudentContentEvalResult",
    "compare_student_content",
    "run_core_eval",
    "run_student_content_eval",
]
