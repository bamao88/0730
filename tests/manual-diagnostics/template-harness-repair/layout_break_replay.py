"""Materialize an unchanged real candidate to verify explicit layout preservation."""

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def replay(task: Path, output: Path) -> dict:
    task, output = task.resolve(), output.resolve()
    assert not output.is_relative_to(task)
    source = task / "input/school-template.docx"
    registry = task / "input/field-registry.yaml"
    inventory = task / "work/.docfit/harness/object-inventory.json"
    review = task / "work/.docfit/harness/semantic-judgments.json"
    bindings = {str(p): sha256_file(p) for p in (source, registry, inventory, review)}
    output.mkdir(parents=True, exist_ok=False)
    (output / "input").mkdir()
    shutil.copy2(source, output / "input/school-template.docx")
    judgments = json.loads(review.read_text())
    assert judgments["semantic_judgments_sha256"] == sha256_json(judgments["semantic_judgments"])
    candidate = output / "diagnostic-template.docx"
    try:
        result = materialize_template_from_semantics(
            source_docx=source,
            output_docx=candidate,
            registry=FieldRegistrySnapshot.load(registry),
            inventory=json.loads(inventory.read_text()),
            review=judgments,
        )
    except ToolFailure as error:
        result = {
            "status": "blocked",
            "failure": {
                "code": error.code,
                "origin": error.origin,
                "message": str(error),
            },
        }
        assert not candidate.exists()
    (output / "materialization.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))

    def breaks(path):
        with zipfile.ZipFile(path) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
        return [node.attrib for node in document.iter(W + "br")]

    unchanged = all(sha256_file(Path(path)) == digest for path, digest in bindings.items())
    assert unchanged
    receipt = {
        "verification_level": "real replay; original judgments, no Agent call or publication",
        "original_bindings": bindings,
        "original_unchanged": unchanged,
        "candidate_sha256": sha256_file(candidate) if candidate.exists() else None,
        "source_breaks": breaks(source),
        "candidate_breaks": breaks(candidate) if candidate.exists() else None,
        "result_summary": {
            k: result.get(k) for k in ("status", "operation_count", "cleanup_count", "failure")
        },
    }
    (output / "replay.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.task, args.output), ensure_ascii=False, indent=2))
