"""Production mapping audit of real initial inventories, no semantic decisions or writes."""

import json
from pathlib import Path
from zipfile import ZipFile

from docfit.template.materialization.runtime import _fragment_text_is_current
from docfit.template.source_spans import (
    SourceSpan,
    TextSourceExtent,
    WholeEntrySourceExtent,
    resolve_source_span,
)
from docfit.template.unit_source import load_initial_inventory
from docfit.tools.runtime import sha256_file
from docfit.tools.word_parts import read_word_stories, resolve_story_locator

base = Path("temp/full-flow-id-20260922")
results = []
for name in ("hunau-initial-read-proof", "njau-initial-read-proof", "pku-initial-read-proof"):
    r = base / name
    with ZipFile(r / "input/school-template.docx") as archive:
        stories = read_word_stories(archive)
    initial = load_initial_inventory(r, sha256_file(r / "input/school-template.docx"))
    canonical = initial["canonical_source_inventory"]
    inv = {
        "document_sha256": canonical["source_snapshot_sha256"],
        "canonical_source_inventory": canonical,
        "source_entries": canonical["source_entries"],
    }
    failed = []
    count = 0
    for entry in canonical["source_entries"]:
        extent = (
            TextSourceExtent(0, len(entry["text"])) if entry["text"] else WholeEntrySourceExtent()
        )
        try:
            resolved = resolve_source_span(
                inventory=inv, source_span=SourceSpan(entry["source_entry_id"], extent)
            )
        except Exception as e:
            failed.append({"source_entry_id": entry["source_entry_id"], "error": str(e)})
            continue
        for fragment in resolved.word_fragments:
            f = fragment.to_json()
            count += 1
            target = resolve_story_locator(stories, f["locator"])
            n = target[1] if target is not None else None
            if n is None or not _fragment_text_is_current(n, f):
                failed.append(
                    {"locator": f["locator"], "expected": f["text"], "resolved": n is not None}
                )
    result = {
        "input": name,
        "source_sha256": canonical["source_snapshot_sha256"],
        "fragments": count,
        "failed": failed,
        "level": "production mapping against actual Word XML; no Agent/write acceptance",
    }
    results.append(result)
    print(name, "fragments", count, "failures", len(failed), failed[:3], flush=True)
    (base / "word-mapping-current.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    )

assert all(not row["failed"] for row in results)
