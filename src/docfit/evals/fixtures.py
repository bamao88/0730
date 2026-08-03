"""Build privacy-safe synthetic DOCX/PDF fixtures from dedicated Python functions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from docfit.tools.image_smoke import make_smoke_png
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import JsonObject, ToolFailure, atomic_write_json, sha256_file
from docfit.tools.service import DocFitToolService


def _run_officecli(*arguments: str) -> None:
    executable = shutil.which("officecli")
    if executable is None:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="officecli_not_found",
            message="Core Eval fixture generation requires the locked OfficeCLI executable.",
        )
    environment = dict(os.environ)
    environment["OFFICECLI_SKIP_UPDATE"] = "1"
    environment["OFFICECLI_RESIDENT_FLUSH"] = "each"
    try:
        completed = subprocess.run(
            [executable, *arguments, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="fixture_officecli_failed",
            message="OfficeCLI could not generate a synthetic Eval fixture.",
        ) from error
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ToolFailure(
            status="error",
            origin="adapter",
            code="fixture_officecli_malformed",
            message="OfficeCLI returned malformed fixture-generation evidence.",
        ) from error
    if (
        completed.returncode != 0
        or not isinstance(payload, dict)
        or payload.get("success") is not True
    ):
        raise ToolFailure(
            status="error",
            origin="engine",
            code="fixture_officecli_rejected",
            message="OfficeCLI rejected a synthetic Eval fixture operation.",
        )


def _create_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run_officecli("create", str(path), "--locale", "zh-CN", "--force")


def _add_paragraph(path: Path, text: str, *, style: str | None = None) -> None:
    arguments = [
        "add",
        str(path),
        "/body",
        "--type",
        "paragraph",
        "--prop",
        f"text={text}",
    ]
    if style:
        arguments.extend(("--prop", f"style={style}"))
    _run_officecli(*arguments)


def _write_simple_pdf(path: Path, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 11 Tf 72 760 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        ),
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, item in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(item)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(payload)


def _build_student(path: Path, marker: Path) -> None:
    _create_docx(path)
    _add_paragraph(path, "Synthetic Thesis Title", style="Title")
    _run_officecli("add", str(path), "/body", "--type", "paragraph")
    _run_officecli(
        "add",
        str(path),
        "/body/p[2]",
        "--type",
        "run",
        "--prop",
        "text=NAME_",
    )
    _run_officecli(
        "add",
        str(path),
        "/body/p[2]",
        "--type",
        "run",
        "--prop",
        "text=SLOT",
    )
    _add_paragraph(path, "1 Introduction", style="Heading1")
    _add_paragraph(path, "Synthetic student body content must be preserved.")
    _run_officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "table",
        "--prop",
        "rows=2",
        "--prop",
        "cols=2",
    )
    _run_officecli(
        "add",
        str(path),
        "/body/p[4]",
        "--type",
        "picture",
        "--prop",
        f"src={marker}",
        "--prop",
        "width=2cm",
    )
    _run_officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "paragraph",
        "--prop",
        "text=Second Page Boundary Marker",
        "--prop",
        "pageBreakBefore=true",
    )


def _build_template(path: Path, marker: Path) -> None:
    _create_docx(path)
    _add_paragraph(path, "SYNTHETIC UNIVERSITY", style="Title")
    _add_paragraph(path, "NAME_SLOT")
    _add_paragraph(path, "INSTRUCTION_TEXT_REMOVE_BEFORE_DELIVERY")
    _add_paragraph(path, "Heading Example", style="Heading1")
    _run_officecli(
        "add",
        str(path),
        "/body/p[1]",
        "--type",
        "picture",
        "--prop",
        f"src={marker}",
        "--prop",
        "width=2cm",
    )


def _object_ref(
    result: JsonObject,
    *,
    text: str | None = None,
    kind: str | None = None,
) -> JsonObject:
    objects = result.get("objects")
    if not isinstance(objects, list):
        raise AssertionError("fixture inspection has no objects")
    for item in objects:
        if not isinstance(item, dict):
            continue
        if text is not None and item.get("text") != text:
            continue
        if kind is not None and item.get("type") != kind:
            continue
        reference = item.get("object_ref")
        if isinstance(reference, dict):
            return reference
    raise AssertionError("fixture object ref was not found")


def build_core_fixtures(repository: Path) -> JsonObject:
    smoke = repository / "evals" / "fixtures" / "smoke"
    risks = repository / "evals" / "fixtures" / "risks"
    smoke.mkdir(parents=True, exist_ok=True)
    risks.mkdir(parents=True, exist_ok=True)
    marker = smoke / "synthetic-marker.png"
    marker.write_bytes(make_smoke_png())
    student = smoke / "student.docx"
    template = smoke / "school-template.docx"
    requirements = smoke / "school-requirements.pdf"
    _build_student(student, marker)
    _build_template(template, marker)
    _write_simple_pdf(
        requirements,
        (
            "Synthetic thesis rules: preserve body; use Heading1 for chapter headings; "
            "replace NAME_SLOT; remove INSTRUCTION_TEXT_REMOVE_BEFORE_DELIVERY."
        ),
    )

    long_title = risks / "blank-page-long-title.docx"
    _create_docx(long_title)
    _add_paragraph(long_title, "Very Long Synthetic Thesis Title " * 20, style="Title")
    _add_paragraph(long_title, "Page boundary evidence follows.")

    complex_objects = risks / "table-picture-layout.docx"
    _build_student(complex_objects, marker)
    stale_ref = risks / "stale-object-ref.docx"
    _create_docx(stale_ref)
    _add_paragraph(stale_ref, "Snapshot identity must expire after an edit.")
    cross_run = risks / "cross-run-placeholder.docx"
    _create_docx(cross_run)
    _run_officecli("add", str(cross_run), "/body", "--type", "paragraph")
    _run_officecli(
        "add",
        str(cross_run),
        "/body/p[1]",
        "--type",
        "run",
        "--prop",
        "text=NAME_",
    )
    _run_officecli(
        "add",
        str(cross_run),
        "/body/p[1]",
        "--type",
        "run",
        "--prop",
        "text=SLOT",
    )

    service = DocFitToolService(office=OfficeCliAdapter())
    student_inspection = service.inspect(
        {"task_root": str(repository), "input_docx": str(student)}
    )
    template_inspection = service.inspect(
        {"task_root": str(repository), "input_docx": str(template)}
    )
    edit_plan = {
        "output_docx": ".tmp/smoke/edited.docx",
        "overwrite": True,
        "operations": [
            {
                "action": "apply_style",
                "target_ref": _object_ref(student_inspection, text="1 Introduction"),
                "style": "Heading1",
            },
            {
                "action": "replace_text",
                "target_ref": _object_ref(student_inspection, text="NAME_SLOT"),
                "expected_text": "NAME_SLOT",
                "replacement": "Synthetic Student",
            },
            {
                "action": "import_template_sections",
                "template_docx": str(template.relative_to(repository)),
                "template_sha256": sha256_file(template),
                "source_refs": [
                    _object_ref(template_inspection, text="SYNTHETIC UNIVERSITY")
                ],
                "insert_anchor_ref": _object_ref(
                    student_inspection,
                    text="Synthetic Thesis Title",
                ),
                "position": "before",
                "include_final_section_properties": False,
            },
        ],
    }
    (repository / ".tmp" / "smoke").mkdir(parents=True, exist_ok=True)
    atomic_write_json(smoke / "edit-plan.json", edit_plan)
    return {
        "student": str(student),
        "template": str(template),
        "requirements": str(requirements),
        "edit_plan": str(smoke / "edit-plan.json"),
        "student_sha256": sha256_file(student),
        "template_sha256": sha256_file(template),
        "requirements_sha256": sha256_file(requirements),
        "risk_fixture_count": 4,
    }
