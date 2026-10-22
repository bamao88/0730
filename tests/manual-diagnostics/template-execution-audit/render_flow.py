"""Render the carrier diagnosis as a small, self-contained execution flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TEMPLATE_PATH = Path(__file__).with_name("flow_template.html")


def render_flow(directory: Path) -> Path:
    report = json.loads((directory / "diagnosis.json").read_text(encoding="utf-8"))
    cases = []
    for index, record in enumerate(report["cases"]):
        case_dir = f"{index:02d}-{record['layout']}-{record['action']}"
        review = json.loads((directory / case_dir / "review.json").read_text(encoding="utf-8"))
        judgment = review["semantic_judgments"][0]
        cases.append({
            **record,
            "directory": case_dir,
            "source_entry_id": judgment["source_entry_id"],
            "parts": judgment["parts"],
            "spans": [
                {
                    "start": span["text_start"],
                    "end": span["text_end"],
                    "role": span["role"],
                    "locators": [fragment["locator"] for fragment in span["word_fragments"]],
                }
                for span in judgment["resolved_spans"]
            ],
        })
    embedded = json.dumps(cases, ensure_ascii=False).replace("<", "\\u003c")
    target = directory / "flow.html"
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    target.write_text(template.replace("__CASES__", embedded), encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Output directory from carrier_diagnosis.py")
    print(render_flow(parser.parse_args().directory))
