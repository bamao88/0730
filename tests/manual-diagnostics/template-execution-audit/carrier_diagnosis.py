"""Constructed carrier differential for attribution, not school replay or acceptance."""

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from render_flow import render_flow

from docfit.template.materialization import materialize_template_from_semantics
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.source_spans import review_resolved_spans_match
from docfit.tools.runtime import ToolFailure, sha256_file
from tests.contract.test_exact_object_cleanup import W, case, part


def control(children, identity):
    return (
        f'<w:sdt><w:sdtPr><w:id w:val="{identity}"/></w:sdtPr>'
        f"<w:sdtContent>{children}</w:sdtContent></w:sdt>"
    )


def diagnose(output):
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for text in ("KeepValue", "甲乙丙丁戊己"):
        plain = f"<w:r><w:t>{text}</w:t></w:r>"
        split = f"<w:r><w:t>{text[:5]}</w:t></w:r><w:r><w:t>{text[5:]}</w:t></w:r>"
        layouts = {
            "direct_run": (plain, "/body/p[1]"),
            "split_runs": (split, "/body/p[1]"),
            "inline_control": (control(split, 1), "/body/p[1]/sdt[1]"),
            "nested_controls": (
                control(control(split, 2), 1),
                "/body/p[1]/sdt[1]/sdtContent[1]/sdt[1]",
            ),
            "hyperlink": (
                f'<w:hyperlink w:anchor="anchor">{split}</w:hyperlink>',
                "/body/p[1]/hyperlink[1]",
            ),
        }
        for layout, (inner, locator) in layouts.items():
            for action in ("partial_fill", "partial_cleanup", "manual_cleanup", "whole_fill"):
                if action == "whole_fill":
                    parts = [part("fill_slot", text, field_id="thesis.title.zh")]
                else:
                    parts = [
                        part(
                            "manual_region" if action == "manual_cleanup" else "fixed_label",
                            text[:4],
                        ),
                        part(
                            "fill_slot" if action == "partial_fill" else "cleanup",
                            text[4:],
                            **({"field_id": "thesis.title.zh"} if action == "partial_fill" else {}),
                        ),
                    ]
                directory = output / f"{len(results):02d}-{layout}-{action}"
                source, registry, inventory, review = case(
                    directory,
                    "<w:p>" + inner + "</w:p>",
                    [("text", locator, text, parts)],
                )
                before = sha256_file(source)
                for name, value in (("inventory", inventory), ("review", review)):
                    (directory / f"{name}.json").write_text(
                        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
                    )
                feedback = materialization_readiness_feedback(
                    inventory=inventory, review=review, registry=registry
                )
                compiled = build_shadow_materialization_plan(
                    inventory=inventory, review=review, registry=registry
                )
                record = {
                    "layout": layout,
                    "text": text,
                    "action": action,
                    "mapping_matches": review_resolved_spans_match(
                        inventory=inventory, semantic_judgments=review["semantic_judgments"]
                    ),
                    "ready": feedback is None,
                    "compiled_ready": compiled.ready,
                    "intent": [i.intent_type.value for i in compiled.intents],
                }
                candidate = directory / "candidate.docx"
                try:
                    materialize_template_from_semantics(
                        source_docx=source,
                        output_docx=candidate,
                        registry=registry,
                        inventory=inventory,
                        review=review,
                    )
                    with zipfile.ZipFile(candidate) as archive:
                        tree = ET.fromstring(archive.read("word/document.xml"))
                    actual = "".join(t.text or "" for t in tree.iter(W + "t"))
                    if action in {"partial_cleanup", "manual_cleanup"}:
                        expected = text[:4]
                    elif action == "partial_fill":
                        expected = text[:4] + "【填】"
                    elif layout in {"inline_control", "nested_controls"}:
                        expected = text  # Complete adoption retains original content.
                    else:
                        expected = "【中文题目】"
                    assert actual == expected, (record, actual, expected)
                    if action in {"partial_fill", "whole_fill"}:
                        fields = [
                            n
                            for n in tree.iter(W + "sdt")
                            if n.find(f"{W}sdtPr/{W}tag") is not None
                        ]
                        assert len(fields) == 1
                        assert (
                            fields[0].find(f"{W}sdtPr/{W}alias").get(W + "val") == "thesis.title.zh"
                        )
                    record.update(result="ok", reopened_effect_checked=True)
                except ToolFailure as error:
                    assert not candidate.exists()
                    record.update(result="failed", code=error.code, origin=error.origin)
                assert sha256_file(source) == before
                results.append(record)
    for left, right in zip(results[:20], results[20:], strict=True):
        assert {k: v for k, v in left.items() if k != "text"} == {
            k: v for k, v in right.items() if k != "text"
        }
    report = {
        "level": "logic/contract; constructed carriers; not real replay or product acceptance",
        "same_outcomes_with_different_wording": True,
        "cases": results,
    }
    (output / "diagnosis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    render_flow(output)
    print(
        json.dumps(
            {
                "cases": len(results),
                "mapping_matches": sum(r["mapping_matches"] for r in results),
                "ready": sum(r["ready"] for r in results),
                "execution_success": sum(r["result"] == "ok" for r in results),
                "execution_failed": sum(r["result"] == "failed" for r in results),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    diagnose(parser.parse_args().output)
