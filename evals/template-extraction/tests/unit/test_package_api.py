from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import template_extraction_eval

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_pkg_01_version_is_explicit() -> None:
    assert template_extraction_eval.__version__ == "0.1.0"


def test_pkg_02_public_exports_are_minimal() -> None:
    assert template_extraction_eval.__all__ == ["__version__"]


def test_pkg_03_import_does_not_load_product_package() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, template_extraction_eval; assert 'docfit' not in sys.modules",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
