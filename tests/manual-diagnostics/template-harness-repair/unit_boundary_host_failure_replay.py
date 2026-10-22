"""Inject a mapping fault into a copy of a real accepted boundary task."""

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path

from docfit.app.prepare_template import PreparedTemplateTask, _unit_boundary_feedback
from docfit.template.unit_source import INITIAL_INVENTORY_PATH
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file
from docfit.tools.service import DocFitToolService


def replay(task: Path, output: Path) -> dict:
    task, output = task.resolve(), output.resolve()
    assert not output.is_relative_to(task)
    checkpoint_path = Path("work/.docfit/unit-boundary-checkpoint.json")
    manifest_path = Path("work/.docfit/prepare-template-task.json")
    watched = [*(task / "input").glob("*"), task / checkpoint_path,
               task / manifest_path, task / INITIAL_INVENTORY_PATH]
    hashes = {str(p): sha256_file(p) for p in watched if p.is_file()}
    checkpoint = json.loads((task / checkpoint_path).read_text())
    assert checkpoint["status"] == "ok"
    units = checkpoint["units"]
    baseline = DocFitToolService(task_root=task).check({
        "check": "unit_coverage", "payload": {"units": units},
    })
    assert baseline["status"] == "ok"
    output.mkdir(parents=True, exist_ok=False)
    copied = output / "task-copy"
    for raw in hashes:
        source = Path(raw)
        target = copied / source.relative_to(task)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    source = copied / "input/school-template.docx"
    registry = copied / "input/field-registry.yaml"
    requirements = copied / "input/school-requirements.pdf"
    prepared = PreparedTemplateTask(
        task_root=copied, template_path=source, registry_source=registry,
        template_sha256=sha256_file(source), registry_sha256=sha256_file(registry),
        requirements_path=requirements if requirements.exists() else None,
        requirements_sha256=sha256_file(requirements) if requirements.exists() else None,
    )
    original = json.loads((copied / INITIAL_INVENTORY_PATH).read_text())
    damaged = deepcopy(original)
    damaged["mapping_digest"] = "0" * 64
    atomic_write_json(copied / INITIAL_INVENTORY_PATH, damaged)
    proposal = {"status": "complete", "units": deepcopy(units)}
    failures = {}
    for seam, check in (
        ("tool", lambda: DocFitToolService(task_root=copied).check({
            "check": "unit_coverage", "payload": {"units": units},
        })),
        ("app_feedback", lambda: _unit_boundary_feedback(prepared, proposal)),
    ):
        try:
            check()
        except ToolFailure as error:
            assert error.origin == "harness"
            assert error.code == "initial_source_inventory_invalid"
            assert not error.retryable
            failures[seam] = error.result()
        else:
            raise AssertionError(f"{seam} did not propagate the host failure")
    assert proposal == {"status": "complete", "units": units}
    atomic_write_json(copied / INITIAL_INVENTORY_PATH, original)
    assert _unit_boundary_feedback(prepared, proposal) is None
    assert proposal["resolved_units"] == baseline["resolved_units"]
    assert hashes == {p: sha256_file(Path(p)) for p in hashes}
    report = {
        "verification_level": "real input fault injection at Tool/App feedback; no Agent call",
        "original_task": str(task), "original_bindings": hashes,
        "original_unchanged": True, "submitted_units_unchanged": proposal["units"] == units,
        "unit_count": len(units), "failures": failures,
        "restored_copy_accepts_original_proposal": True,
        "natural_failure": False, "e2e_agent_loop": False, "product_acceptance": False,
    }
    atomic_write_json(output / "replay.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.task, args.output)
    print(json.dumps({k: report[k] for k in (
        "verification_level", "unit_count", "original_unchanged",
        "restored_copy_accepts_original_proposal",
    )}, ensure_ascii=False))
