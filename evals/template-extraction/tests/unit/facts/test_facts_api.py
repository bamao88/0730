from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import stable_data

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def test_fapi_01_public_analyzer_returns_unified_facts() -> None:
    facts = analyze_docx(FIXTURES / "S00-minimal-pass" / "gold-template.docx")
    assert facts.document_sha256
    assert len(facts.paragraphs) == 1
    assert len(facts.controls) == 1


def test_fapi_02_actual_and_gold_share_the_same_stable_shape() -> None:
    root = FIXTURES / "S00-minimal-pass"
    actual = stable_data(analyze_docx(root / "actual-template.docx"))
    gold = stable_data(analyze_docx(root / "gold-template.docx"))
    assert actual.keys() == gold.keys()
    assert actual == gold


def test_fapi_03_import_has_no_product_or_office_side_effect() -> None:
    code = (
        "import sys; import template_extraction_eval.facts; "
        "assert 'docfit' not in sys.modules; "
        "assert not any(name.startswith('adobe') for name in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

