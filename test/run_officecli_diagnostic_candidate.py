"""Produce a test-only diagnostic candidate after docx_edit fails to publish."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from docfit.tools.inspection import inspect_document, resolve_object_ref
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package


TASK_ROOT = Path(__file__).resolve().parent
SOURCE = TASK_ROOT / "input" / "school-template-nannong-undergraduate.docx"
PLAN = TASK_ROOT / "work" / "clean-plan.json"
OUTPUT = TASK_ROOT / "work" / "diagnostic-clean-template-candidate.docx"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    office = OfficeCliAdapter()
    source_hash = sha256(SOURCE)
    inspection = inspect_document(SOURCE, office)
    operations = json.loads(PLAN.read_text(encoding="utf-8"))["operations"]
    commands: list[dict[str, object]] = []

    for operation in operations:
        target = resolve_object_ref(operation["target_ref"], inspection)
        expected = operation["expected_text"]
        if expected not in target.text:
            raise ValueError("an edit precondition is not satisfied")
        commands.append(
            {
                "command": "set",
                "path": target.locator,
                "props": {
                    "find": expected,
                    "replace": operation["replacement"],
                },
            }
        )

    shutil.copyfile(SOURCE, OUTPUT)
    OUTPUT.chmod(0o600)
    office.batch(OUTPUT, commands)
    validate_docx_package(OUTPUT)
    office.validate(OUTPUT)
    if sha256(SOURCE) != source_hash:
        raise RuntimeError("source template changed")

    print(
        json.dumps(
            {
                "status": "diagnostic_candidate_only",
                "operation_count": len(commands),
                "source_sha256": source_hash,
                "candidate_sha256": sha256(OUTPUT),
                "source_unchanged": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
