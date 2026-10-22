from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
body_log = root / "body-resume-from-boundary.log"
assert body_log.stat().st_size, "Wait for the actual CLI completion before freezing evidence."
snapshot = root / "body-resume-final"
snapshot.mkdir(exist_ok=False)
body_state = root / "body-task" / "work" / ".docfit"
for source in [body_log, body_state / "template-agent-execution.json",
               body_state / "harness/semantic-batch-candidates.json",
               body_state / "harness/semantic-batch-manifest.json",
               body_state / "harness/object-inventory.json",
               body_state / "unit-boundary-checkpoint.json",
               body_state / "tool-call-audit.jsonl"]:
    shutil.copy2(source, snapshot / source.name)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
integrity = {"skill": {}, "inputs": {}}
for name, expected in manifest["skill_sha256"].items():
    actual = sha(Path(name))
    integrity["skill"][name] = {"expected": expected, "actual": actual, "matches": actual == expected}
for case, config in manifest["cases"].items():
    integrity["inputs"][case] = {}
    for name, expected in config["input_sha256"].items():
        actual = sha(root / (case + "-package") / "input" / name)
        integrity["inputs"][case][name] = {"expected": expected, "actual": actual, "matches": actual == expected}
outcomes = {}
for case in ["cover", "body"]:
    task = root / (case + "-task")
    state = task / "work" / ".docfit"
    trace = json.loads((state / "template-agent-execution.json").read_text())
    ledger = json.loads((state / "harness/semantic-batch-candidates.json").read_text())
    result_events = [e for e in trace.get("sdk_events", []) if e.get("message_type") == "ResultMessage"]
    outcomes[case] = {
        "trace_status": trace.get("status"),
        "failure": trace.get("failure"),
        "sdk_query_count": trace.get("sdk_query_count"),
        "semantic_feedback_attempts": trace.get("semantic_feedback_attempts"),
        "harness_feedback_attempts": trace.get("harness_feedback_attempts"),
        "wall_duration_ms": trace.get("wall_duration_ms"),
        "last_public_result": result_events[-1] if result_events else None,
        "candidate_count": ledger.get("candidate_count"),
        "candidate_sha256": sha(state / "harness/semantic-batch-candidates.json"),
        "accepted_judgments_present": (state / "harness/semantic-judgments.json").exists(),
        "final_template_present": (task / "output/final-template.docx").exists(),
        "fill_contract_present": (task / "output/fill-contract.yaml").exists(),
        "read_tool_count": trace.get("tool_uses", []).count("Read"),
    }
history = json.loads((root / "run-history.json").read_text())
history["attempts"][-1].update({"status": outcomes["body"]["trace_status"], "exit_code": int(sys.argv[1]), "evidence_dir": snapshot.name, "failure": outcomes["body"]["failure"]})
(root / "run-history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")
result = {
    "finished_at": datetime.now(timezone.utc).isoformat(),
    "code_commit_at_finish": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "integrity": integrity,
    "outcomes": outcomes,
    "final_snapshot_sha256": {p.name: sha(p) for p in snapshot.iterdir() if p.is_file()},
}
(root / "final-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
(root / "stop-observer").touch()
print(json.dumps({"outcomes": outcomes, "all_skill_hashes_match": all(v["matches"] for v in integrity["skill"].values()), "all_input_hashes_match": all(v["matches"] for case in integrity["inputs"].values() for v in case.values())}, ensure_ascii=False, indent=2))
