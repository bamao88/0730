from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time

root = Path(__file__).resolve().parent
out = root / "observed-ledgers" / "final-window"
out.mkdir(parents=True, exist_ok=True)
live = root / "body-task" / "work" / ".docfit"
names = ["harness/semantic-batch-candidates.json", "template-agent-execution.json", "harness/semantic-judgments.json"]
seen = {}
deadline = time.monotonic() + 1800
while time.monotonic() < deadline and not (root / "stop-observer").exists():
    for name in names:
        source = live / name
        if not source.exists():
            continue
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if seen.get(name) == digest:
            continue
        try:
            json.loads(data)
        except (ValueError, UnicodeDecodeError):
            continue
        stamp = datetime.now(timezone.utc)
        snapshot = out / (stamp.strftime("%H%M%S%f") + "-" + source.name)
        snapshot.write_bytes(data)
        event = {"observed_at": stamp.isoformat(), "case": "body", "source": str(source), "snapshot": str(snapshot), "sha256": digest}
        with (out / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        seen[name] = digest
        print(json.dumps({"changed": name, "snapshot": snapshot.name}), flush=True)
    time.sleep(3)
print("final-window observer stopped", flush=True)
