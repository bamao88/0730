#!/usr/bin/env python3
"""Sync Gold DOCX hashes and comment-count metadata for template extraction cases."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path("evals/template-extraction/cases")

CASES = {
    "01-hunau-undergraduate": {
        "object_comments": 43,
        "coverage_comments": 184,
        "visible_body_blocks": 183,
        "header_footer_visible_blocks": 1,
    },
    "02-njau-undergraduate": {
        "object_comments": 39,
        "coverage_comments": 57,
        "visible_body_blocks": 56,
        "header_footer_visible_blocks": 10,
    },
    "03-pku-graduate": {
        "object_comments": 42,
        "coverage_comments": 117,
        "visible_body_blocks": 116,
        "header_footer_visible_blocks": 10,
    },
}

APPROVED_AT = "2026-08-18T13:20:00+08:00"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_word_review_block(text: str, data: dict[str, int]) -> str:
    total = data["object_comments"] + data["coverage_comments"]
    block = (
        "    word_review_comments:\n"
        "      review_status: coverage_completed_pending_manual_recheck\n"
        "      authors:\n"
        "        - Codex Gold Review\n"
        "        - Codex Gold Coverage Review\n"
        f"      object_review_comment_count: {data['object_comments']}\n"
        f"      coverage_comment_count: {data['coverage_comments']}\n"
        f"      total_comment_count: {total}\n"
        f"      visible_body_blocks: {data['visible_body_blocks']}\n"
        f"      header_footer_visible_blocks: {data['header_footer_visible_blocks']}\n"
        "      scope: slots_regions_styles_logical_pages_and_all_visible_body_blocks_plus_header_footer_summary\n"
    )
    updated, count = re.subn(
        r"^    word_review_comments:\n(?:      .*\n)+",
        block,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError("word_review_comments block not found")
    return updated


def main() -> None:
    for case_id, data in CASES.items():
        case_root = ROOT / case_id
        template = case_root / "gold" / "final-template.gold.docx"
        contract = case_root / "gold" / "fill-contract.gold.yaml"
        case_yaml = case_root / "case.yaml"
        receipt = case_root / "candidate-package-receipt.json"
        review_docx = (
            case_root / "review" / "accepted-2026-08-17" / "reviewed-final-template.gold.docx"
        )
        approval_record = case_root / "review" / "accepted-2026-08-17" / "approval-record.yaml"

        new_template_sha = sha256(template)
        contract_text = contract.read_text()
        old_template_sha = re.search(
            r"^template_sha256: ([0-9a-f]{64})$", contract_text, flags=re.MULTILINE
        ).group(1)
        contract_text = contract_text.replace(old_template_sha, new_template_sha)
        contract_text = replace_word_review_block(contract_text, data)
        contract.write_text(contract_text)

        new_contract_sha = sha256(contract)
        case_text = case_yaml.read_text()
        old_contract_sha = re.search(
            r"^  contract_sha256: ([0-9a-f]{64})$", case_text, flags=re.MULTILINE
        ).group(1)
        case_text = case_text.replace(old_template_sha, new_template_sha)
        case_text = case_text.replace(old_contract_sha, new_contract_sha)
        case_yaml.write_text(case_text)

        new_case_sha = sha256(case_yaml)
        receipt_data = json.loads(receipt.read_text())
        receipt_data["case_sha256"] = new_case_sha
        receipt_data["contract_sha256"] = new_contract_sha
        receipt_data["template_sha256"] = new_template_sha
        receipt.write_text(json.dumps(receipt_data, ensure_ascii=False, indent=2) + "\n")

        if review_docx.exists() and approval_record.exists():
            shutil.copyfile(template, review_docx)
            total = data["object_comments"] + data["coverage_comments"]
            approval_record.write_text(
                "\n".join(
                    [
                        "schema_version: docfit-template-extraction-gold-approval/v1",
                        f"case_id: {case_id}",
                        "approved_by: xpw",
                        f"approved_at: '{APPROVED_AT}'",
                        "approval_conclusion: approved_gold_pair_with_post_approval_comment_coverage_fix",
                        "approval_note: user_reported_comment_coverage_gap; coverage_comments_completed_pending_manual_recheck",
                        "reviewed_word:",
                        "  path: review/accepted-2026-08-17/reviewed-final-template.gold.docx",
                        f"  sha256: {new_template_sha}",
                        "  relation_to_gold_template: byte_identical_snapshot_after_coverage_review",
                        "  word_comments:",
                        "    review_status: coverage_completed_pending_manual_recheck",
                        "    authors:",
                        "      - Codex Gold Review",
                        "      - Codex Gold Coverage Review",
                        f"    object_review_comment_count: {data['object_comments']}",
                        f"    coverage_comment_count: {data['coverage_comments']}",
                        f"    total_comment_count: {total}",
                        f"    visible_body_blocks: {data['visible_body_blocks']}",
                        f"    header_footer_visible_blocks: {data['header_footer_visible_blocks']}",
                        "    scope: slots_regions_styles_logical_pages_and_all_visible_body_blocks_plus_header_footer_summary",
                        "gold_pair:",
                        "  template:",
                        "    path: gold/final-template.gold.docx",
                        f"    sha256: {new_template_sha}",
                        "  contract:",
                        "    path: gold/fill-contract.gold.yaml",
                        f"    sha256: {new_contract_sha}",
                        "retention:",
                        "  keep_reviewed_word_snapshot: true",
                        "  keep_gold_pair: true",
                        "  purpose: future_issue_triage_and_gold_optimization_baseline",
                        "",
                    ]
                )
            )

        print(
            f"{case_id}: template={new_template_sha} "
            f"contract={new_contract_sha} case={new_case_sha}"
        )


if __name__ == "__main__":
    main()
