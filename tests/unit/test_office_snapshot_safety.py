from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from docfit.app.agent import project_root
from docfit.tools.inspection import inspect_document_snapshot
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import JsonObject, sha256_file

ROOT = project_root()
TEMPLATE = ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"


def _dirty_docx(path: Path, marker: str) -> None:
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(f"docProps/{marker}.txt", marker)


class _MutatingQueryOffice:
    def query(self, document: Path, _selector: str) -> tuple[JsonObject, ...]:
        _dirty_docx(document, "mutated-query")
        return ()

    def evidence(self) -> JsonObject:
        return {"name": "mutating-query"}


class _MutatingValidateOffice(OfficeCliAdapter):
    def __init__(self) -> None:
        pass

    def validate(self, document: Path) -> JsonObject:
        _dirty_docx(document, "mutated-validate")
        return {"passed": True, "detail": "mutated private snapshot"}


def test_inspection_snapshot_does_not_dirty_source_docx(tmp_path: Path) -> None:
    document = tmp_path / "source.docx"
    shutil.copyfile(TEMPLATE, document)
    document.chmod(0o444)
    before = sha256_file(document)

    inspection = inspect_document_snapshot(
        document,
        _MutatingQueryOffice(),  # type: ignore[arg-type]
        selector="paragraph",
    )

    assert inspection.document_sha256 == before
    assert sha256_file(document) == before
    assert document.stat().st_mode & 0o777 == 0o444


def test_office_validate_snapshot_does_not_dirty_source_docx(tmp_path: Path) -> None:
    document = tmp_path / "source.docx"
    shutil.copyfile(TEMPLATE, document)
    document.chmod(0o444)
    before = sha256_file(document)

    result = _MutatingValidateOffice().validate_snapshot(document)

    assert result["passed"] is True
    assert sha256_file(document) == before
    assert document.stat().st_mode & 0o777 == 0o444
