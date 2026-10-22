"""Host-owned final-page review evidence; image generation is not a review verdict."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from docfit.tools.runtime import ToolFailure, atomic_write_json, read_json, sha256_file, sha256_json
from docfit.visual.evidence import EvidenceStore
from docfit.visual.service import VisualEvidenceService

JsonObject = dict[str, Any]
REVIEW_SCHEMA = "docfit-final-visual-review/v1"
CRITERIA = (
    "content_completeness_and_pagination",
    "overflow_and_overlap",
    "text_direction",
    "tables_and_formulas",
    "protected_layout",
)


def _stop(code: str, message: str, *, pending: bool = False) -> ToolFailure:
    return ToolFailure(
        status="needs_input" if pending else "error",
        origin="application",
        code=code,
        message=message,
        retryable=pending,
        suggested_actions=(
            "Review the saved final-page evidence and record actual observations before resuming.",
            "Do not change school semantic judgments to bypass the final visual review.",
        ),
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_final_visual_review(
    review: JsonObject,
    *,
    candidate_hash: str,
    source_hash: str,
    store: EvidenceStore,
) -> None:
    """Require a verdict, page observations and intact current render evidence.

    This validates the review contract, not whether a person or external visual
    reviewer's conclusions are true. Product signoff remains a separate decision.
    """
    if review.get("schema_version") != REVIEW_SCHEMA:
        raise _stop("final_visual_review_missing", "A final-page review record is required.")
    if (
        review.get("document_sha256") != candidate_hash
        or review.get("source_document_sha256") != source_hash
    ):
        raise _stop("final_visual_review_stale", "The review belongs to a different Word version.")
    if review.get("status") != "passed":
        raise _stop(
            "final_visual_review_not_passed",
            "The final visual review is pending, blocked or requires further inspection.",
            pending=review.get("status") in ("pending", "uncertain"),
        )
    reviewer = review.get("reviewer")
    if (
        not isinstance(reviewer, dict)
        or reviewer.get("kind") not in ("human", "external_visual_reviewer")
        or not _nonempty(reviewer.get("name"))
        or not _nonempty(reviewer.get("reviewed_at"))
    ):
        raise _stop("final_visual_reviewer_missing", "The actual reviewer and date are required.")
    try:
        reviewed_at = datetime.fromisoformat(reviewer["reviewed_at"])
        if reviewed_at.tzinfo is None:
            raise ValueError("timezone missing")
    except ValueError as error:
        raise _stop(
            "final_visual_reviewer_invalid", "The review date must include its timezone."
        ) from error
    _, manifest = store.resolve_render(review.get("render_ref"))
    _, source_manifest = store.resolve_render(review.get("source_render_ref"))
    for expected_hash, rendered in ((candidate_hash, manifest), (source_hash, source_manifest)):
        if (
            rendered.get("document_sha256") != expected_hash
            or rendered.get("fidelity") != "approximate"
            or not isinstance(rendered.get("renderer"), dict)
            or rendered["renderer"].get("name") != "libreoffice"
        ):
            raise _stop(
                "final_visual_render_invalid", "The review lacks current fixed-render evidence."
            )
    page_count = manifest.get("page_count")
    if type(page_count) is not int or page_count < 1:
        raise _stop("final_visual_page_count_invalid", "The final render has no valid page count.")
    pages = review.get("pages")
    if not isinstance(pages, list) or len(pages) != page_count:
        raise _stop("final_visual_pages_incomplete", "Every final page requires an actual review.")
    seen: set[int] = set()
    for row in pages:
        if not isinstance(row, dict) or type(row.get("page")) is not int:
            raise _stop("final_visual_page_invalid", "A final-page review is malformed.")
        page = row["page"]
        if page not in range(1, page_count + 1) or page in seen:
            raise _stop(
                "final_visual_pages_incomplete", "Final pages must be reviewed exactly once."
            )
        seen.add(page)
        view = store.resolve_view(row.get("evidence_ref"))
        identity = view.metadata.get("identity", {})
        if (
            view.metadata.get("render_ref") != review["render_ref"]
            or view.metadata.get("page") != page
            or not isinstance(identity, dict)
            or identity.get("view") != "page"
            or identity.get("dpi") not in (144, 220)
        ):
            raise _stop(
                "final_visual_page_evidence_invalid",
                "A reviewed page has unrelated image evidence.",
            )
        checks = row.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(CRITERIA):
            raise _stop("final_visual_observations_missing", "Page review criteria are incomplete.")
        for criterion in CRITERIA:
            result = checks[criterion]
            if (
                not isinstance(result, dict)
                or result.get("status") not in ("passed", "not_applicable")
                or (
                    result.get("status") == "not_applicable"
                    and criterion not in ("text_direction", "tables_and_formulas")
                )
                or not _nonempty(result.get("observation"))
            ):
                raise _stop(
                    "final_visual_observations_incomplete",
                    "Every page criterion needs an observation and a resolved conclusion.",
                )
    findings = review.get("findings")
    if not isinstance(findings, list) or any(
        not isinstance(item, dict)
        or item.get("status") != "resolved"
        or item.get("blocking") is True
        or item.get("severity") == "blocking"
        or not _nonempty(item.get("resolution"))
        for item in findings
    ):
        raise _stop("final_visual_findings_unresolved", "The review contains unresolved findings.")


def _page_evidence(visual: VisualEvidenceService, rendered: JsonObject) -> list[JsonObject]:
    page_count = rendered.get("page_count")
    if type(page_count) is not int or page_count < 1:
        raise _stop("final_visual_page_count_invalid", "The rendered document has no valid pages.")
    rows: list[JsonObject] = []
    for first in range(1, page_count + 1, 4):
        result, _ = visual.review(
            {
                "render_ref": rendered["render_ref"],
                "mode": "pages",
                "quality": "review",
                "pages": list(range(first, min(first + 4, page_count + 1))),
            }
        )
        for evidence in result["evidence"]:
            stored = visual.store.resolve_view(evidence["evidence_ref"])
            rows.append(
                {
                    "page": stored.metadata["page"],
                    "evidence_ref": stored.reference,
                    "image_path": str(stored.path.relative_to(visual.task_root)),
                }
            )
    if [row["page"] for row in rows] != list(range(1, page_count + 1)):
        raise _stop("final_visual_pages_incomplete", "Rendering did not provide every page image.")
    return rows


def require_final_visual_review(
    *,
    task_root: Path,
    source_docx: Path,
    candidate_docx: Path,
    visual: VisualEvidenceService | None = None,
) -> JsonObject:
    """Prepare all evidence before requiring a human/external review, then resume.

    No runtime semantic Agent is asked to invent a visual-review receipt. The
    default has no automatic visual reviewer; this method never fabricates one.
    """
    visual = visual or VisualEvidenceService(task_root)
    source_hash, candidate_hash = sha256_file(source_docx), sha256_file(candidate_docx)
    source_render, _ = visual.render({"input_docx": str(source_docx), "overview": False})
    candidate_render, _ = visual.render({"input_docx": str(candidate_docx), "overview": False})
    identity = {
        "source_document_sha256": source_hash,
        "document_sha256": candidate_hash,
        "source_render_ref": source_render["render_ref"],
        "render_ref": candidate_render["render_ref"],
    }
    directory = task_root / "work/.docfit/final-visual-review" / sha256_json(identity)
    directory.mkdir(parents=True, exist_ok=True)
    receipt = directory / "review.json"
    candidate_pages = _page_evidence(visual, candidate_render)
    packet = {
        "schema_version": "docfit-final-visual-review-request/v1",
        **identity,
        "source_pages": _page_evidence(visual, source_render),
        "candidate_pages": candidate_pages,
        "review_path": str(receipt.relative_to(task_root)),
        "criteria": list(CRITERIA),
        "instructions": (
            "Inspect every final page against the source and intended semantic changes. "
            "Check missing or unintended blank pages, pagination, overflow, overlap, "
            "text direction, "
            "tables, formulas and protected layout. Record actual per-page observations. "
            "LibreOffice is approximate; unresolved Word-rendering ambiguity "
            "requires further review. "
            "This review does not sign off the product."
        ),
        "accepted_semantics_path": "work/.docfit/harness/semantic-judgments.json",
        "review_template": {
            "schema_version": REVIEW_SCHEMA,
            **identity,
            "status": "pending",
            "reviewer": {"kind": "human", "name": "", "reviewed_at": ""},
            "pages": [
                {
                    "page": row["page"],
                    "evidence_ref": row["evidence_ref"],
                    "checks": {key: {"status": "pending", "observation": ""} for key in CRITERIA},
                }
                for row in candidate_pages
            ],
            "findings": [],
        },
    }
    atomic_write_json(directory / "request.json", packet)
    atomic_write_json(
        task_root / "work/.docfit/final-visual-review/current.json",
        {
            **identity,
            "request_path": str((directory / "request.json").relative_to(task_root)),
            "review_path": str(receipt.relative_to(task_root)),
        },
    )
    if not receipt.is_file():
        raise _stop(
            "final_visual_review_required",
            (
                f"Final-page images are ready. Review {directory / 'request.json'} "
                f"and save actual conclusions to {receipt}."
            ),
            pending=True,
        )
    review = read_json(receipt)
    validate_final_visual_review(
        review, candidate_hash=candidate_hash, source_hash=source_hash, store=visual.store
    )
    if (
        review["render_ref"] != identity["render_ref"]
        or review["source_render_ref"] != identity["source_render_ref"]
    ):
        raise _stop(
            "final_visual_review_stale", "The review uses a previous rendering environment."
        )
    return {**review, "reviewed_pages": [row["page"] for row in review["pages"]]}
