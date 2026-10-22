"""CLI adapter for Candidate Package preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .candidate_package import build_candidate_packages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build hash-bound template-extraction candidate packages."
    )
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    receipts = build_candidate_packages(
        args.source_manifest,
        args.output_root,
        case_ids=args.case_ids,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "receipts": [
                    {
                        "case_id": receipt.case_id,
                        "case_root": receipt.case_root.as_posix(),
                        "case_sha256": receipt.case_sha256,
                        "template_sha256": receipt.template_sha256,
                        "contract_sha256": receipt.contract_sha256,
                        "gold_review_status": receipt.gold_review_status,
                        "written": receipt.written,
                    }
                    for receipt in receipts
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
