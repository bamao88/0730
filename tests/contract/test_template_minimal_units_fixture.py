from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest
import yaml

from docfit.tools.service import DocFitToolService

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evals/fixtures/template-extraction/minimal-units-0820"
BUILDER = FIXTURE / "build_input_package.py"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest() -> dict[str, Any]:
    data = yaml.safe_load((FIXTURE / "manifest.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _run_builder(units: str, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--units",
            units,
            "--output",
            str(output),
            "--force",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _selected_selectors(output: Path) -> list[str]:
    selected = yaml.safe_load(
        (output / "input/selected-units.yaml").read_text(encoding="utf-8")
    )
    assert selected["schema_version"] == "docfit-template-extraction-selected-input/v1"
    return [unit["selector"] for unit in selected["selected_units"]]


def _body_counts(docx: Path) -> tuple[int, int]:
    with zipfile.ZipFile(docx) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    body = document.find(f"{{{W_NS}}}body")
    assert body is not None
    paragraphs = sum(1 for child in body if child.tag == f"{{{W_NS}}}p")
    tables = sum(1 for child in body if child.tag == f"{{{W_NS}}}tbl")
    return paragraphs, tables


def test_minimal_units_manifest_is_hash_bound() -> None:
    manifest = _manifest()

    assert manifest["schema_version"] == "docfit-template-extraction-minimal-units/v1"
    assert manifest["fixture_id"] == "hunau-minimal-units-0820"
    assert "runtime oracle" in " ".join(manifest["not_intended_use"])
    units = manifest["units"]
    assert [unit["selector"] for unit in units] == [
        "01-cover",
        "02-integrity-statement",
        "03-toc",
        "04-paper-body",
        "05-design-task",
        "06-proposal",
    ]

    for unit in units:
        docx = FIXTURE / unit["source_docx"]
        pdf = FIXTURE / unit["source_pdf"]
        assert docx.is_file()
        assert pdf.is_file()
        assert _sha256(docx) == unit["docx_sha256"]
        assert _sha256(pdf) == unit["pdf_sha256"]


@pytest.mark.parametrize(
    ("selector", "minimum_body_paragraphs"),
    [
        ("01-cover", 20),
        ("04-paper-body", 60),
    ],
    ids=["cover", "paper-body"],
)
def test_minimal_unit_builder_creates_single_input_package_for_key_units(
    tmp_path: Path,
    selector: str,
    minimum_body_paragraphs: int,
) -> None:
    output = tmp_path / selector
    result = _run_builder(selector, output)
    assert result.returncode == 0, result.stderr

    assert _selected_selectors(output) == [selector]
    assert (output / "input/school-template.docx").is_file()
    assert (output / "input/school-requirements.pdf").is_file()
    assert (output / "input/field-registry.yaml").is_file()

    paragraphs, _tables = _body_counts(output / "input/school-template.docx")
    assert paragraphs >= minimum_body_paragraphs


def test_paper_body_input_package_is_consumable_by_docfit_inspect(tmp_path: Path) -> None:
    if shutil.which("officecli") is None:
        pytest.skip("docfit inspect requires the local officecli executable")

    output = tmp_path / "paper-body"
    result = _run_builder("04-paper-body", output)
    assert result.returncode == 0, result.stderr

    service = DocFitToolService(task_root=output)
    inspection = service.inspect(
        {
            "task_root": str(output),
            "input_docx": "input/school-template.docx",
            "output": "inspect-paper-body.json",
            "include_objects": False,
        }
    )

    assert inspection["status"] == "ok"
    assert inspection["document"]["paragraphs"] >= 60
    assert inspection["object_count"] >= 60
    assert (output / "inspect-paper-body.json").is_file()


def test_minimal_unit_builder_creates_multi_input_package(tmp_path: Path) -> None:
    if shutil.which("pdfunite") is None:
        pytest.skip("pdfunite is required for multi-unit PDF package checks")

    multi = tmp_path / "multi"
    result = _run_builder("01-cover,03-toc,04-paper-body", multi)
    assert result.returncode == 0, result.stderr

    assert _selected_selectors(multi) == [
        "01-cover",
        "03-toc",
        "04-paper-body",
    ]
    with zipfile.ZipFile(multi / "input/school-template.docx") as archive:
        assert "word/document.xml" in archive.namelist()
    assert (multi / "input/school-requirements.pdf").read_bytes().startswith(b"%PDF")
