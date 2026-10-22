"""Replay a real rejected unit proposal through Tool and Agent-visible feedback."""

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from docfit.app.prepare_template import (
    PreparedTemplateTask,
    _agent_visible_feedback_packet,
    build_unit_boundary_checkpoint_prompt,
)
from docfit.tools.runtime import sha256_file
from docfit.tools.service import DocFitToolService


def replay(task: Path, output: Path) -> dict:
    task, output = task.resolve(), output.resolve()
    assert not output.is_relative_to(task)
    checkpoint = task / "work/.docfit/unit-boundary-checkpoint.json"
    source, registry = task / "input/school-template.docx", task / "input/field-registry.yaml"
    requirements = task / "input/school-requirements.pdf"
    watched = [*(task / "input").glob("*"), *(task / "work/.docfit").rglob("*.json")]
    hashes = {str(p): sha256_file(p) for p in watched if p.is_file()}
    original = json.loads(checkpoint.read_text())
    units = original["last_structured_output"]["units"]
    before = deepcopy(units)
    feedback = DocFitToolService(task_root=task).check({
        "check": "unit_coverage", "payload": {"units": units},
    })
    visible = _agent_visible_feedback_packet(feedback, next_step="Revise only unit boundaries.")
    prepared = PreparedTemplateTask(
        task_root=task, template_path=source,
        requirements_path=requirements if requirements.exists() else None,
        registry_source=registry, template_sha256=sha256_file(source),
        requirements_sha256=sha256_file(requirements) if requirements.exists() else None,
        registry_sha256=sha256_file(registry),
    )
    prompt = build_unit_boundary_checkpoint_prompt(prepared, feedback)
    assert units == before
    assert hashes == {p: sha256_file(Path(p)) for p in hashes}
    result = {
        "verification_level": "real replay of original rejected unit proposal; no Agent call",
        "original_bindings": hashes, "original_unchanged": True,
        "submitted_units_unchanged": True, "original_feedback": original["feedback"],
        "new_feedback": feedback, "agent_visible_feedback": visible,
        "diagnostic_counts": dict(Counter(i["code"] for i in visible.get("affected", []))),
        "product_acceptance": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "replay.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (output / "revision-prompt.txt").write_text(prompt)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.task, args.output)
    print(json.dumps({k: result[k] for k in (
        "verification_level", "diagnostic_counts", "original_unchanged",
    )}, ensure_ascii=False))
