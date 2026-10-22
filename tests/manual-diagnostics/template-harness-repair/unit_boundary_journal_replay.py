"""Record two real historical proposals as a labelled replay, never invented run history."""

import argparse
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from docfit.app.prepare_template import (
    PreparedTemplateTask,
    _unit_boundary_feedback,
    build_unit_boundary_checkpoint_prompt,
)
from docfit.template.unit_boundary_journal import UnitBoundaryJournal, read_unit_boundary_journal
from docfit.template.unit_source import INITIAL_INVENTORY_PATH
from docfit.tools.runtime import atomic_write_json, read_json, sha256_file


def replay(rejected_task: Path, accepted_task: Path, output: Path) -> dict:
    tasks = [rejected_task.resolve(), accepted_task.resolve()]
    output = output.resolve()
    assert all(not output.is_relative_to(task) for task in tasks)
    watched = []
    for task in tasks:
        watched.extend((task / "input").glob("*"))
        watched.extend(task / p for p in (
            "work/.docfit/unit-boundary-checkpoint.json", str(INITIAL_INVENTORY_PATH),
            "work/.docfit/prepare-template-task.json",
        ))
    hashes = {str(p): sha256_file(p) for p in watched if p.is_file()}
    checkpoints = [read_json(task / "work/.docfit/unit-boundary-checkpoint.json") for task in tasks]
    assert checkpoints[0]["status"] == "needs_input" and checkpoints[1]["status"] == "ok"
    proposals = [checkpoints[0]["last_structured_output"], {
        "status": "complete", "units": checkpoints[1]["units"],
        "summary": checkpoints[1].get("summary", ""),
    }]
    source = tasks[1] / "input/school-template.docx"
    assert sha256_file(tasks[0] / "input/school-template.docx") == sha256_file(source)
    assert read_json(tasks[0] / INITIAL_INVENTORY_PATH) == read_json(
        tasks[1] / INITIAL_INVENTORY_PATH
    )
    registry = tasks[1] / "input/field-registry.yaml"
    requirements = tasks[1] / "input/school-requirements.pdf"
    prepared = PreparedTemplateTask(
        task_root=tasks[1], template_path=source, registry_source=registry,
        template_sha256=sha256_file(source), registry_sha256=sha256_file(registry),
        requirements_path=requirements if requirements.exists() else None,
        requirements_sha256=sha256_file(requirements) if requirements.exists() else None,
    )
    output.mkdir(parents=True, exist_ok=False)
    journal = UnitBoundaryJournal(output / uuid4().hex, binding={
        "evidence_mode": "replay", "source_sha256": prepared.template_sha256,
        "historical_tasks": [str(task) for task in tasks],
    })
    feedback = None
    for index, original in enumerate(proposals):
        submitted = deepcopy(original)
        request = journal.record("request", {
            "prompt": build_unit_boundary_checkpoint_prompt(prepared, feedback),
            "feedback": feedback, "constructed_for_replay": True,
        })
        response = journal.record("response", {
            "request_sequence": request, "structured_output": submitted,
            "source_task": str(tasks[index]), "historical_proposal_only": True,
        })
        feedback = _unit_boundary_feedback(prepared, submitted)
        assert (feedback is None) is (index == 1)
        journal.record("review", {"response_sequence": response, "feedback": feedback})
    restored = read_unit_boundary_journal(journal.directory, binding=journal.binding)
    assert restored == journal.events
    assert [e["data"]["structured_output"] for e in restored
            if e["kind"] == "response"] == proposals
    assert restored[4]["data"]["diff"]["units"]
    assert hashes == {p: sha256_file(Path(p)) for p in hashes}
    report = {
        "verification_level": "real proposal replay through Tool/App feedback and boundary journal",
        "original_bindings": hashes, "original_unchanged": True,
        "event_count": len(restored),
        "changed_unit_positions": len(restored[4]["data"]["diff"]["units"]),
        "rejected_then_accepted": True, "recorded_submissions_unmodified": True,
        "history": str(journal.directory), "constructed_replay_sequence": True,
        "original_prompts_available": False, "agent_called": False,
        "natural_revision": False, "product_acceptance": False,
    }
    atomic_write_json(output / "verification.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rejected-task", type=Path, required=True)
    parser.add_argument("--accepted-task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.rejected_task, args.accepted_task, args.output)
    print({k: report[k] for k in (
        "verification_level", "event_count", "changed_unit_positions", "original_unchanged",
    )})
