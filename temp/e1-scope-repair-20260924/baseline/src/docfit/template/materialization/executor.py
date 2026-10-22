"""OOXML package write executor for template materialization."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file


def write_materialized_docx(
    *,
    source_docx: Path,
    output_docx: Path,
    document_xml: bytes,
    part_updates: dict[str, bytes] | None = None,
) -> JsonObject:
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_docx.name}.",
        suffix=".tmp",
        dir=output_docx.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with (
            zipfile.ZipFile(source_docx) as source,
            zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as target,
        ):
            updates = {**(part_updates or {}), "word/document.xml": document_xml}
            if not set(updates).issubset(source.namelist()):
                raise ToolFailure(
                    status="needs_input",
                    origin="harness",
                    code="word_story_part_missing",
                    message="Cannot write an unknown Word package part.",
                )
            for item in source.infolist():
                payload = updates.get(item.filename, source.read(item))
                target.writestr(item, payload)
        validate_docx_package(temporary)
        os.replace(temporary, output_docx)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "schema_version": 1,
        "status": "ok",
        "executor": "ooxml_executor",
        "output_docx": str(output_docx),
        "output_sha256": sha256_file(output_docx),
        "package_validation": "ok",
    }
