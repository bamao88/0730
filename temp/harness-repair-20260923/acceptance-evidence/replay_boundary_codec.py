"""Re-encode explicit accepted text only; never infer whitespace from source."""
import copy
import hashlib
import itertools
import json
from pathlib import Path

from docfit.template.harness import OBJECT_INVENTORY_PATH, _decode_whitespace_parts
from docfit.template.batch_review import batch_text_feedback
from docfit.template.source_spans import SourceSpan, TextSourceExtent, WholeEntrySourceExtent, resolve_source_span, source_span_ref

ROOT = Path(__file__).resolve().parents[1]

def runs(text):
    return [{"codepoint": f"U+{ord(char):04X}", "count": len(list(group))}
            for char, group in itertools.groupby(text)]

def resolve_accepted_subset(inventory, judgments):
    # The school run stopped before all entries were judged. Use the production
    # batch gate, then resolve each explicit accepted part against the full inventory.
    assert batch_text_feedback(inventory=inventory, judgments=judgments,
        required_source_entry_ids=tuple(j['source_entry_id'] for j in judgments)) is None
    resolved = []
    for judgment in judgments:
        cursor = 0
        for part in judgment['parts']:
            end = cursor + len(part['text'])
            extent = TextSourceExtent(cursor, end) if part['text'] else WholeEntrySourceExtent()
            span = SourceSpan(judgment['source_entry_id'], extent)
            exact = resolve_source_span(inventory=inventory, source_span=span)
            ref = source_span_ref(source_snapshot_sha256=exact.source_snapshot_sha256, source_span=span)
            resolved.append({'exact': exact, 'span_ref': ref, 'role': part['role'],
                **({'slot_ref': ref + ';field_id=' + part['field_id']} if part.get('field_id') else {})})
            cursor = end
    return resolved

report = {"verification_level": "real replay of source-valid recorded candidate entries with boundary whitespace; deterministic representation conversion, not new Agent output or whole-school acceptance", "schools": []}
for name in ["phase5-three-schools/pku-graduate-task", "phase2-live-20260923/body-task", "phase2-live-20260923/cover-task"]:
    task = ROOT / name
    inv_path = task / OBJECT_INVENTORY_PATH
    inventory = json.loads(inv_path.read_text())
    accepted = [(p, json.loads(p.read_text())) for p in sorted((task / "work/.docfit/harness/semantic-revisions").glob("[0-9]*.json"))]
    accepted = [(p, e) for p, e in accepted if e["kind"] == "candidate_recorded"]
    event_path, event = accepted[-1]
    raw = [j for c in event["data"]["ledger"]["candidates"] for j in c["semantic_judgments"]]
    original, failure = _decode_whitespace_parts(raw)
    assert failure is None
    # Old candidate events were not necessarily checked by the newer local gate.
    # Select the boundary-bearing entries, then report and exclude entries whose
    # original text already fails current validation. Never repair their semantics.
    original = [j for j in original if any(p['text'].strip() and p['text'] != p['text'].strip() for p in j['parts'])]
    excluded = []
    valid = []
    for j in original:
        feedback = batch_text_feedback(inventory=inventory, judgments=[j], required_source_entry_ids=(j['source_entry_id'],))
        if feedback is None:
            valid.append(j)
        else:
            excluded.append({'source_entry_id': j['source_entry_id'], 'blockers': feedback['blockers']})
    original = valid
    encoded = copy.deepcopy(original)
    changed = []
    for judgment in encoded:
        for index, part in enumerate(judgment["parts"]):
            text = part["text"]
            if not text.strip() or text == text.strip():
                continue
            left = len(text) - len(text.lstrip())
            right = len(text.rstrip())
            part["text"] = text[left:right]
            if left:
                part["leading_whitespace"] = runs(text[:left])
            if right != len(text):
                part["trailing_whitespace"] = runs(text[right:])
            changed.append({"source_entry_id": judgment["source_entry_id"], "part_index": index, "role": part["role"], "field_id": part.get("field_id")})
    decoded, failure = _decode_whitespace_parts(encoded)
    assert changed, "This case must exercise boundary re-encoding, not just legacy compatibility"
    assert failure is None and decoded == original
    before = resolve_accepted_subset(inventory, original)
    after = resolve_accepted_subset(inventory, decoded)
    assert before == after
    paths = [inv_path, event_path, task / "input/school-template.docx"]
    report["schools"].append({"task": str(task), "judgment_count": len(original), "changed_parts": changed, "excluded_invalid_original_entries": excluded,
        "span_count": len(after), "slot_count": sum("slot_ref" in s for s in after),
        "exact_judgments_and_resolved_spans_equal": True,
        "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})
out = Path(__file__).with_name("part-boundary-real-replay.json")
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps([{ "task": Path(s["task"]).name, "judgments": s["judgment_count"], "changed_parts": len(s["changed_parts"]), "slots": s["slot_count"]} for s in report["schools"]]))
