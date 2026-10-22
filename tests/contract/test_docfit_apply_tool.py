from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools import docfit_apply
from docfit.tools.inspection import InspectedObject, Inspection
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from docfit.tools.service import DocFitToolService
from tests.support.source_identity import persist_source_identity, review_binding, source_partition


def _task_root(tmp_path: Path) -> tuple[Path, str, Path]:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    (root / "work").mkdir(parents=True)
    (root / "output").mkdir()
    source.write_bytes(b"PK\x03\x04source")
    _write_registry(root, field_ids=("thesis.title.zh",))
    return root, sha256_file(source), source


def _write_registry(root: Path, *, field_ids: tuple[str, ...]) -> None:
    fields = [
        {
            "field_id": field_id,
            "label": field_id,
            "meaning": "test field",
            "content_type": "text",
        }
        for field_id in field_ids
    ]
    (root / "input/field-registry.json").write_text(
        json.dumps(
            {
                "registry_id": "docfit.test.fields",
                "registry_version": "0.1.0",
                "fields": fields,
            }
        ),
        encoding="utf-8",
    )


def _write_foreign_registry(root: Path, relative: str) -> str:
    return _write_json(
        root,
        relative,
        {
            "registry_id": "docfit.foreign.fields",
            "registry_version": "0.1.0",
            "fields": [
                {
                    "field_id": "thesis.title.zh",
                    "label": "foreign title",
                    "meaning": "foreign test field",
                    "content_type": "text",
                }
            ],
        },
    )


def _write_body_structure_registry(root: Path) -> None:
    (root / "input/field-registry.json").write_text(
        json.dumps(
            {
                "registry_id": "docfit.test.fields",
                "registry_version": "0.1.0",
                "fields": [
                    {
                        "field_id": "body.chapters",
                        "label": "body.chapters",
                        "meaning": "body section",
                        "content_type": "section",
                    },
                    {
                        "field_id": "body.heading.outline1",
                        "label": "body.heading.outline1",
                        "meaning": "body heading",
                        "content_type": "text",
                        "parent_field_id": "body.chapters",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _object_ref(document_hash: str, object_id: str = "obj-target") -> dict[str, str]:
    return {
        "document_sha256": document_hash,
        "object_id": object_id,
        "expected_fingerprint": "f" * 64,
    }


def _span_ref(
    *,
    block_id: str = "u-cover:block-0001",
    part_index: int = 0,
) -> str:
    return f"source_entry_id=source-entry-{block_id};part_index={part_index}"


def _slot_ref(
    field_id: str,
    *,
    block_id: str = "u-cover:block-0001",
    part_index: int = 0,
) -> str:
    return f"{_span_ref(block_id=block_id, part_index=part_index)};field_id={field_id}"


def _target_json(
    document_hash: str,
    *,
    object_id: str = "obj-target",
    carrier: str = "paragraph",
    text: str = "学校封面",
    locator: str = "/body/p[1]",
    ancestor_object_ids: list[str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "object_ref": _object_ref(document_hash, object_id),
        "type": carrier,
        "text": text,
        "locator": locator,
    }
    if ancestor_object_ids is not None:
        payload["ancestor_object_ids"] = ancestor_object_ids
    return json.dumps(payload, ensure_ascii=False)


def _write_json(root: Path, relative: str, payload: object) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return relative


def _write_action_package(
    root: Path,
    relative: str,
    operation: dict[str, Any],
) -> str:
    return _write_json(
        root,
        relative,
        {
            "field_registry": "input/field-registry.json",
            "operations": [operation],
        },
    )


def _write_unit_checkpoint(root: Path, source_hash: str) -> None:
    inventory = {
        "document_sha256": source_hash,
        "source_entries": [
            {
                "source_entry_id": "source-entry-test-cover",
                "text": "学校封面",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {"object_id": "obj-target", "locator": "/body/p[1]", "text_span": [0, 4]}
                ],
            }
        ],
    }
    source_partition(inventory, unit_id="u-cover", unit_name="cover")
    persist_source_identity(root, inventory)


def _write_phase_review(
    root: Path,
    document_hash: str,
    *,
    duplicate_resolved_span: bool = False,
    parts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    vocabulary = FieldRegistrySnapshot.load(
        root / "input/field-registry.json"
    ).pre_input_vocabulary()
    block_id = "u-cover:block-0001"
    source_entry_id = f"source-entry-{block_id}"
    range_id = "u-cover:range-0001"
    object_ids = ["obj-target"]
    if parts is None:
        parts = [
            {
                "text": "学校封面",
                "role": "fill_slot",
                "field_id": "thesis.title.zh",
            }
        ]
    block_text = "".join(str(part.get("text", "")) for part in parts)
    _write_json(
        root,
        "work/.docfit/harness/object-inventory.json",
        {
            "schema_version": 2,
            "document_sha256": document_hash,
            "object_count": 1,
            "source_entry_count": 1,
            "reading_block_count": 1,
            "source_entries": [
                {
                    "source_entry_id": source_entry_id,
                    "text": block_text,
                    "entry_type": "text",
                    "source_order": {"block": 1, "inline": 0},
                    "provenance": [
                        {
                            "object_id": "obj-target",
                            "locator": "/body/p[1]",
                            "text_span": [0, len(block_text)],
                        }
                    ],
                }
            ],
            "objects": [
                {
                    "object_id": "obj-target",
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "source_entry_id": source_entry_id,
                }
            ],
            "reading_blocks": [
                {
                    "block_id": block_id,
                    "range_id": range_id,
                    "unit_id": "u-cover",
                    "text": block_text,
                    "covered_object_ids": object_ids,
                    "object_text_spans": [
                        {
                            "object_id": "obj-target",
                            "text": block_text,
                            "text_start": 0,
                            "text_end": len(block_text),
                        }
                    ],
                }
            ],
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
        },
    )
    inventory = json.loads(
        (root / "work/.docfit/harness/object-inventory.json").read_text(encoding="utf-8")
    )
    agent_judgments = [{"source_entry_id": source_entry_id, "parts": parts}]
    source_partition(inventory, unit_id="u-cover", unit_name="cover")
    persist_source_identity(root, inventory)
    _write_json(root, "work/.docfit/harness/object-inventory.json", inventory)
    resolved_spans = resolve_semantic_judgments(
        inventory=inventory,
        judgments=agent_judgments,
    )
    judgments = [{**agent_judgments[0], "resolved_spans": resolved_spans}]
    if duplicate_resolved_span:
        judgments[0]["resolved_spans"].append(
            {
                **judgments[0]["resolved_spans"][0],
                "span_ref": f"{_span_ref(block_id=block_id, part_index=0)};duplicate=1",
            }
        )
    _write_json(
        root,
        "work/.docfit/harness/semantic-judgments.json",
        {
            **review_binding(inventory),
            "schema_version": 2,
            "semantic_judgments_sha256": sha256_json(judgments),
            "document_sha256": document_hash,
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
            "judgment_count": 1,
            "covered_object_count": 1,
            "semantic_judgments": judgments,
            "resolved_spans": resolved_spans,
        },
    )
    return resolved_spans


def _fake_inspection(document_hash: str) -> Inspection:
    target = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="学校封面",
        style=None,
        format={},
        object_ref=_object_ref(document_hash),
    )
    return Inspection(
        document_sha256=document_hash,
        objects=(target,),
        summary={},
        risks=(),
        warnings=(),
        provider={"name": "fake-office"},
    )


def _write_legacy_phase_review(root: Path, document_hash: str) -> None:
    _write_json(
        root,
        "work/.docfit/harness/semantic-judgments.json",
        {
            "schema_version": 2,
            "semantic_judgments_sha256": "j" * 64,
            "document_sha256": document_hash,
            "judgment_count": 1,
            "covered_object_count": 1,
            "semantic_judgments": [
                {
                    "judgment_id": "j-cover",
                    "responsibility": "fill_interface",
                    "covered_object_ids": ["obj-target"],
                    "registry_field": {"field_id": "thesis.title.zh"},
                }
            ],
        },
    )


def _real_task_root(tmp_path: Path) -> tuple[Path, str, Path]:
    root = tmp_path / "real-task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    (root / "work").mkdir(parents=True)
    (root / "output").mkdir()
    shutil.copyfile(
        Path(__file__).resolve().parents[2] / "evals/fixtures/smoke/school-template.docx",
        source,
    )
    _write_registry(root, field_ids=("author.name.zh",))
    return root, sha256_file(source), source


def _fake_edit(root: Path, seen: list[dict[str, Any]]):
    def edit(args: dict[str, Any]) -> dict[str, Any]:
        seen.append(args)
        output = root / str(args["output_docx"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            b"PK\x03\x04candidate" + json.dumps(args, sort_keys=True).encode("utf-8")
        )
        return {
            "schema_version": 1,
            "status": "ok",
            "committed": True,
            "checks": [{"name": "fake_edit", "result": "ok"}],
            "warnings": [],
            "failure": None,
            "output_sha256": sha256_file(output),
            "output_docx": str(output),
            "operations": [{"index": 0, "result": "applied"}],
        }

    return edit


def test_t3_docfit_apply_handler_is_the_single_canonical_write_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert docfit_apply.annotations.readOnlyHint is False

    class _FakeService:
        def apply(self, _args: dict[str, object]) -> dict[str, object]:
            return {
                "schema_version": "docfit_apply_receipt_v1",
                "status": "ok",
                "committed": True,
                "completion": False,
                "candidate_hash": "b" * 64,
                "receipt": {"operation": "clear_content"},
                "invalidated_evidence": [],
                "checks": [],
                "warnings": [],
                "failure": None,
            }

    monkeypatch.setattr("docfit.tools.DocFitToolService", _FakeService)

    result = asyncio.run(
        docfit_apply.handler(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": "a" * 64,
                "batch_ref": "work/fake-action.json",
                "output_docx": "work/candidate.docx",
            }
        )
    )

    structured = result["structuredContent"]
    assert structured["status"] == "ok"
    assert structured["committed"] is True
    assert structured["completion"] is False


def test_t3_evidence_objects_expose_canonical_string_target_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash},
            "objects": [
                {
                    "object_ref": _object_ref(source_hash),
                    "type": "paragraph",
                    "text": "学校封面",
                    "locator": "/body/p[1]",
                }
            ],
            "object_count": 1,
            "object_window": {"returned": 1, "total": 1, "has_more": False},
            "risks": [],
            "failure": None,
        },
    )

    result = service.evidence({"focus": "object_detail"})

    target_ref = result["evidence"][0]["target_ref"]
    assert isinstance(target_ref, str)
    assert target_ref.startswith("object_ref:")


def test_t3_apply_defaults_source_hash_from_bound_task_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "edit", _fake_edit(root, seen))
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/default-source-hash-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(target_ref),
        },
    )

    result = service.apply(
        {
            "schema_version": "docfit_apply_input_v1",
            "candidate_hash": source_hash,
            "batch_ref": batch_ref,
            "output_docx": "work/default-source-hash.docx",
        }
    )

    assert result["status"] == "ok"
    assert result["source_hash"] == source_hash
    assert seen[-1]["input_docx"] == "input/school-template.docx"


def test_t3_apply_rejects_retired_source_hash_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("retired source_hash must fail before edit"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "source_hash": source_hash,
                "candidate_hash": source_hash,
                "batch_ref": "work/unused-action.json",
                "output_docx": "work/source-hash-retired.docx",
            }
        )

    assert failure.value.code == "schema_envelope_invalid"
    assert "source_hash" in failure.value.message
    assert failure.value.retryable is True


@pytest.mark.parametrize(
    "legacy_field",
    (
        "semantic_field",
        "query",
        "registry_field",
        "field_id",
        "target_ref",
        "object_ref",
        "locator",
        "paragraph",
        "paragraph_index",
        "scope_ref",
        "source_entry_id",
        "span_ref",
        "slot_ref",
        "reading_block_id",
        "reading_range_id",
        "range_id",
        "operation",
        "operations",
        "edit_operation",
        "target_refs",
        "replacement_text",
        "style_contract_ref",
        "evidence_ref",
        "field_registry",
    ),
)
def test_t3_apply_explicitly_rejects_legacy_direct_write_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_field: str,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("legacy direct input must fail before edit"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": "work/unused-action.json",
                "output_docx": "work/legacy-direct-input.docx",
                legacy_field: "legacy-value",
            }
        )

    assert failure.value.code == "schema_envelope_invalid"
    assert legacy_field in failure.value.message
    assert failure.value.retryable is True


def test_t3_materialize_slot_requires_harness_slot_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("slot_ref validation must fail before edit"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/missing-slot-ref-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/missing-slot-ref.docx",
            }
        )

    assert failure.value.code == "slot_ref_missing"


def test_t3_apply_field_write_requires_phase_review_even_without_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("field write must fail before edit"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/no-checkpoint-field-write-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": _slot_ref("thesis.title.zh"),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/no-checkpoint-field-write.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_apply_requires_reviewed_action_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("action package gate must fail before edit"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "output_docx": "work/no-action-package.docx",
            }
        )

    assert failure.value.code == "action_package_required"


def test_t3_post_unit_apply_rejects_action_package_missing_field_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("missing package registry must fail before edit"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_json(
        root,
        "work/missing-package-registry-action.json",
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "target_ref": json.loads(target_ref),
                    "field_id": "thesis.title.zh",
                    "slot_ref": _slot_ref("thesis.title.zh"),
                }
            ],
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/missing-package-registry.docx",
            }
        )

    assert failure.value.code == "field_registry_missing"
    assert "field_id_vocabulary" in failure.value.message


def test_t3_apply_rejects_retired_singular_edit_operation_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("retired action package must fail before edit"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_json(
        root,
        "work/retired-singular-action.json",
        {
            "edit_operation": {
                "action": "materialize_slot",
                "target_ref": json.loads(target_ref),
                "field_id": "thesis.title.zh",
                "slot_ref": _slot_ref("thesis.title.zh"),
            }
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/retired-singular-action.docx",
            }
        )

    assert failure.value.code == "action_package_shape_retired"


def test_t3_direct_docx_edit_post_unit_materialize_slot_requires_phase_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        "docfit.tools.service.inspect_document_snapshot",
        lambda *_args, **_kwargs: _fake_inspection(source_hash),
    )
    monkeypatch.setattr(
        "docfit.tools.service.mutate_objects",
        lambda *_args, **_kwargs: pytest.fail("docx_edit must fail before writing"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.edit(
            {
                "input_docx": "input/school-template.docx",
                "output_docx": "work/direct-docx-edit-no-review.docx",
                "field_registry": "input/field-registry.json",
                "operations": [
                    {
                        "action": "materialize_slot",
                        "target_ref": _object_ref(source_hash),
                        "field_id": "thesis.title.zh",
                        "slot_ref": _slot_ref("thesis.title.zh"),
                    }
                ],
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_direct_docx_edit_post_unit_materialize_slot_requires_accepted_slot_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        "docfit.tools.service.inspect_document_snapshot",
        lambda *_args, **_kwargs: _fake_inspection(source_hash),
    )
    monkeypatch.setattr(
        "docfit.tools.service.mutate_objects",
        lambda *_args, **_kwargs: pytest.fail("docx_edit must fail before writing"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.edit(
            {
                "input_docx": "input/school-template.docx",
                "output_docx": "work/direct-docx-edit-unaccepted-slot.docx",
                "field_registry": "input/field-registry.json",
                "operations": [
                    {
                        "action": "materialize_slot",
                        "target_ref": _object_ref(source_hash),
                        "field_id": "thesis.title.zh",
                        "slot_ref": (
                            "source_entry_id=source-entry-u-cover:block-0001;"
                            f"extent=text[0:3];source_snapshot_sha256={source_hash};"
                            "field_id=thesis.title.zh"
                        ),
                    }
                ],
            }
        )

    assert failure.value.code == "phase_review_action_package_unaccepted"


def test_t3_direct_docx_edit_post_unit_materialize_slot_requires_input_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        "docfit.tools.service.inspect_document_snapshot",
        lambda *_args, **_kwargs: _fake_inspection(source_hash),
    )
    monkeypatch.setattr(
        "docfit.tools.service.mutate_objects",
        lambda *_args, **_kwargs: pytest.fail("docx_edit must fail before writing"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.edit(
            {
                "input_docx": "input/school-template.docx",
                "output_docx": "work/direct-docx-edit-missing-registry.docx",
                "operations": [
                    {
                        "action": "materialize_slot",
                        "target_ref": _object_ref(source_hash),
                        "field_id": "thesis.title.zh",
                        "slot_ref": _slot_ref("thesis.title.zh"),
                    }
                ],
            }
        )

    assert failure.value.code == "field_registry_missing"
    assert "field_id_vocabulary" in failure.value.message


def test_t3_direct_docx_edit_post_unit_materialize_slot_rejects_registry_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    foreign_registry = _write_foreign_registry(root, "work/foreign-field-registry.json")
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        "docfit.tools.service.inspect_document_snapshot",
        lambda *_args, **_kwargs: _fake_inspection(source_hash),
    )
    monkeypatch.setattr(
        "docfit.tools.service.mutate_objects",
        lambda *_args, **_kwargs: pytest.fail("docx_edit must fail before writing"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.edit(
            {
                "input_docx": "input/school-template.docx",
                "output_docx": "work/direct-docx-edit-foreign-registry.docx",
                "field_registry": foreign_registry,
                "operations": [
                    {
                        "action": "materialize_slot",
                        "target_ref": _object_ref(source_hash),
                        "field_id": "thesis.title.zh",
                        "slot_ref": _slot_ref("thesis.title.zh"),
                    }
                ],
            }
        )

    assert failure.value.code == "field_registry_not_pre_input"


def test_t3_apply_receipt_uses_packaged_action_for_candidate_hash_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "edit", _fake_edit(root, seen))
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/clear-content-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(target_ref),
        },
    )

    result = service.apply(
        {
            "schema_version": "docfit_apply_input_v1",
            "candidate_hash": source_hash,
            "batch_ref": batch_ref,
            "output_docx": "work/clear-content.docx",
            "idempotency_key": "t3-clear-content",
        }
    )

    assert result["schema_version"] == "docfit_apply_receipt_v1"
    assert result["status"] == "ok"
    assert result["committed"] is True
    assert result["completion"] is False
    assert result["candidate_hash"] == sha256_file(root / "work/clear-content.docx")
    assert result["receipt"]["operation"] == "clear_content"
    assert result["receipt"]["edit_action"] == "clear_content"
    assert result["invalidated_evidence"]
    assert "published" not in result
    assert "style_contract" not in result
    assert seen and seen[-1]["operations"][0]["action"] == "clear_content"


def test_t3_post_unit_apply_requires_phase_review_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("post-unit gate must fail before edit"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/no-phase-review-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": _slot_ref("thesis.title.zh"),
        },
    )

    with pytest.raises(ToolFailure) as missing_review:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/no-action-requirement.docx",
            }
        )

    assert missing_review.value.code == "phase_review_required"
    assert missing_review.value.retryable is True
    assert any("Harness phase review" in item for item in missing_review.value.suggested_actions)
    assert not any(
        "action_requirement" in item or "docfit_check(action_plan)" in item
        for item in missing_review.value.suggested_actions
    )


def test_t3_post_unit_apply_accepts_accepted_phase_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    resolved_spans = _write_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "edit", _fake_edit(root, seen))
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/with-phase-review-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": resolved_spans[0]["slot_ref"],
        },
    )

    result = service.apply(
        {
            "schema_version": "docfit_apply_input_v1",
            "candidate_hash": source_hash,
            "batch_ref": batch_ref,
            "output_docx": "work/with-phase-review.docx",
            "idempotency_key": "with-phase-review",
        }
    )

    assert result["status"] == "ok"
    assert seen and seen[-1]["operations"][0]["action"] == "materialize_slot"


def test_t3_post_unit_apply_allows_span_covering_text_object_not_carrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["object_count"] = 2
    inventory["objects"] = [
        {
            "object_id": "obj-carrier",
            "type": "paragraph",
            "locator": "/body/p[1]",
            "source_entry_id": "source-entry-u-cover:block-0001",
        },
        {
            "object_id": "obj-target",
            "type": "run",
            "locator": "/body/p[1]/r[1]",
            "source_entry_id": "source-entry-u-cover:block-0001",
        },
    ]
    inventory["source_entries"][0]["provenance"] = [
        {
            "object_id": "obj-carrier",
            "locator": "/body/p[1]",
            "text_span": [0, len("学校封面")],
        },
        {
            "object_id": "obj-target",
            "locator": "/body/p[1]/r[1]",
            "text_span": [0, len("学校封面")],
        },
    ]
    inventory.pop("canonical_source_inventory")
    source_partition(inventory)
    persist_source_identity(root, inventory)
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    agent_judgments = [
        {key: value for key, value in judgment.items() if key != "resolved_spans"}
        for judgment in review["semantic_judgments"]
    ]
    source_partition(inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=agent_judgments,
    )
    review["semantic_judgments"] = [{**agent_judgments[0], "resolved_spans": resolved}]
    review["resolved_spans"] = resolved
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review.update(review_binding(inventory))
    review_path.write_text(json.dumps(review), encoding="utf-8")
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "edit", _fake_edit(root, seen))
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/text-object-span-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": resolved[0]["slot_ref"],
        },
    )

    result = service.apply(
        {
            "schema_version": "docfit_apply_input_v1",
            "candidate_hash": source_hash,
            "batch_ref": batch_ref,
            "output_docx": "work/text-object-span.docx",
            "idempotency_key": "text-object-span",
        }
    )

    assert result["status"] == "ok"
    assert seen[-1]["output_docx"] == "work/text-object-span.docx"


def test_t3_post_unit_apply_rejects_legacy_phase_review_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_legacy_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("legacy phase review must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/legacy-review-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": _slot_ref("thesis.title.zh"),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/legacy-review.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_conflicting_resolved_spans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash, duplicate_resolved_span=True)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("conflicting phase review must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/conflicting-review-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": _slot_ref("thesis.title.zh"),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/conflicting-review.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_span_field_without_part_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(
        root,
        source_hash,
        parts=[{"text": "学校封面", "role": "manual_region"}],
    )
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["semantic_judgments"][0]["resolved_spans"][0]["field_id"] = "thesis.title.zh"
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review_path.write_text(json.dumps(review), encoding="utf-8")
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("non-field span field_id must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/non-field-span-field-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(target_ref),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/non-field-span-field.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


@pytest.mark.parametrize(
    "span_patch",
    (
        {"text": "source was rewritten after Agent judgment"},
        {"role": "fill_slot"},
    ),
)
def test_t3_post_unit_apply_rejects_resolved_span_part_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    span_patch: dict[str, object],
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(
        root,
        source_hash,
        parts=[{"text": "学校封面", "role": "manual_region"}],
    )
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["semantic_judgments"][0]["resolved_spans"][0].update(span_patch)
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review_path.write_text(json.dumps(review), encoding="utf-8")
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("mismatched resolved span must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/mismatched-span-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(target_ref),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/mismatched-span.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_resolved_span_objects_outside_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(
        root,
        source_hash,
        parts=[{"text": "学校封面", "role": "manual_region"}],
    )
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["semantic_judgments"][0]["resolved_spans"][0]["covered_object_ids"] = [
        "obj-outside-scope"
    ]
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review_path.write_text(json.dumps(review), encoding="utf-8")
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("out-of-scope resolved span must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/out-of-scope-span-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(target_ref),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/out-of-scope-span.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_resolved_span_missing_scope_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(
        root,
        source_hash,
        parts=[{"text": "学校封面", "role": "manual_region"}],
    )
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["object_count"] = 2
    inventory["objects"].append(
        {
            "object_id": "obj-unresolved",
            "type": "run",
            "locator": "/body/p[1]/r[2]",
        }
    )
    inventory["reading_blocks"][0]["covered_object_ids"].append("obj-unresolved")
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("incomplete resolved span must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/incomplete-span-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(target_ref),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/incomplete-span.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_review_without_object_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    (root / "work/.docfit/harness/object-inventory.json").unlink()
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("review without inventory must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/missing-inventory-review-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": _slot_ref("thesis.title.zh"),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/missing-inventory-review.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_forged_review_vocabulary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["field_id_vocabulary"] = {
        "allowed_field_ids": ["thesis.title.zh"],
        "digest": "v" * 64,
    }
    review["field_vocabulary_digest"] = "v" * 64
    review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("forged vocabulary must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/forged-vocabulary-review-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": _slot_ref("thesis.title.zh"),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/forged-vocabulary-review.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_review_with_uncovered_inventory_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["objects"].append(
        {
            "object_id": "obj-uncovered",
            "type": "paragraph",
            "locator": "/body/p[2]",
        }
    )
    inventory["object_count"] = 2
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False),
        encoding="utf-8",
    )
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("uncovered inventory object must not unlock apply"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/uncovered-inventory-review-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": _slot_ref("thesis.title.zh"),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/uncovered-inventory-review.docx",
            }
        )

    assert failure.value.code == "phase_review_required"


def test_t3_post_unit_apply_rejects_unreviewed_packaged_slot_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_registry(root, field_ids=("thesis.title.zh", "author.name.zh"))
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("unreviewed package slot must not call edit"),
    )
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/unreviewed-slot-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "author.name.zh",
            "slot_ref": (
                "source_entry_id=source-entry-u-cover:block-0001;"
                f"extent=text[0:4];source_snapshot_sha256={source_hash};"
                "field_id=author.name.zh"
            ),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/unreviewed-slot.docx",
            }
        )

    assert failure.value.code == "phase_review_action_package_unaccepted"


def test_t3_post_unit_materialize_structure_uses_reviewed_batch_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_body_structure_registry(root)
    _write_unit_checkpoint(root, source_hash)
    resolved_spans = _write_phase_review(
        root,
        source_hash,
        parts=[
            {
                "text": "一级标题",
                "role": "body_structure",
                "field_id": "body.heading.outline1",
            },
        ],
    )
    batch_ref = _write_action_package(
        root,
        "work/materialize-structure-action.json",
        {
            "action": "materialize_structure",
            "target_ref": _object_ref(source_hash),
            "structure_ref": "body.chapters",
            "members": [
                {
                    "target_ref": _object_ref(source_hash),
                    "field_id": "body.heading.outline1",
                    "slot_ref": resolved_spans[0]["slot_ref"],
                }
            ],
        },
    )
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "edit", _fake_edit(root, seen))

    result = service.apply(
        {
            "schema_version": "docfit_apply_input_v1",
            "candidate_hash": source_hash,
            "batch_ref": batch_ref,
            "output_docx": "work/reviewed-materialize-structure.docx",
            "idempotency_key": "reviewed-materialize-structure",
        }
    )

    assert result["status"] == "ok"
    assert seen[-1]["field_registry"] == "input/field-registry.json"
    assert seen[-1]["operations"] == [
        {
            "action": "materialize_structure",
            "target_ref": _object_ref(source_hash),
            "structure_ref": "body.chapters",
            "members": [
                {
                    "target_ref": _object_ref(source_hash),
                    "field_id": "body.heading.outline1",
                    "slot_ref": resolved_spans[0]["slot_ref"],
                }
            ],
        }
    ]


def test_t3_post_unit_materialize_structure_rejects_parent_slot_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_body_structure_registry(root)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(
        root,
        source_hash,
        parts=[
            {
                "text": "一级标题",
                "role": "body_structure",
                "field_id": "body.heading.outline1",
            }
        ],
    )
    batch_ref = _write_action_package(
        root,
        "work/materialize-structure-old-parent-slot-action.json",
        {
            "action": "materialize_structure",
            "target_ref": _object_ref(source_hash),
            "field_id": "body.chapters",
            "slot_ref": _slot_ref("body.chapters"),
            "members": [
                {
                    "target_ref": _object_ref(source_hash),
                    "field_id": "body.heading.outline1",
                    "slot_ref": _slot_ref("body.heading.outline1"),
                }
            ],
        },
    )
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(service, "edit", lambda _args: pytest.fail("old package must fail"))

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/old-reviewed-materialize-structure.docx",
                "idempotency_key": "old-reviewed-materialize-structure",
            }
        )

    assert failure.value.code == "body_structure_parent_slot_ref_retired"


def test_t3_post_unit_apply_rejects_action_package_field_registry_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_phase_review(root, source_hash)
    foreign_registry = _write_foreign_registry(root, "work/foreign-field-registry.json")
    batch_ref = _write_json(
        root,
        "work/foreign-registry-action.json",
        {
            "field_registry": foreign_registry,
            "operations": [
                {
                    "action": "materialize_slot",
                    "target_ref": _object_ref(source_hash),
                    "field_id": "thesis.title.zh",
                    "slot_ref": _slot_ref("thesis.title.zh"),
                }
            ],
        },
    )
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("docfit_apply must fail before docx_edit"),
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/reject-foreign-registry.docx",
            }
        )

    assert failure.value.code == "field_registry_not_pre_input"


def test_t3_apply_fails_closed_on_stale_refs_and_source_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("precondition failure must not call edit"),
    )

    stale_ref = _write_action_package(
        root,
        "work/stale-target-action.json",
        {
            "action": "clear_content",
            "target_ref": _target_json("b" * 64),
        },
    )
    with pytest.raises(ToolFailure) as stale_target:
        service.apply(
            {
                "candidate_hash": source_hash,
                "batch_ref": stale_ref,
                "output_docx": "work/stale-target.docx",
            }
        )
    assert stale_target.value.code == "stale_object_ref"

    source.write_bytes(b"PK\x03\x04changed")
    with pytest.raises(ToolFailure) as stale_source:
        service.apply(
            {
                "candidate_hash": source_hash,
                "output_docx": "work/stale-source.docx",
            }
        )
    assert stale_source.value.code == "stale_ref"


def test_t3_invalid_target_ref_feedback_is_retryable_with_rebuild_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("precondition failure must not call edit"),
    )

    batch_ref = _write_action_package(
        root,
        "work/invalid-target-action.json",
        {
            "action": "clear_content",
            "target_ref": "object_ref:not-valid-base64",
        },
    )

    with pytest.raises(ToolFailure) as invalid_target:
        service.apply(
            {
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/invalid-target.docx",
            }
        )

    assert invalid_target.value.code == "target_ref_invalid"
    assert invalid_target.value.retryable is True
    assert any(
        "current candidate document" in item for item in invalid_target.value.suggested_actions
    )


def test_t3_apply_fails_closed_on_typoed_carrier_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _real_task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("precondition failure must not call edit"),
    )

    objects = service.inspect({"input_docx": str(_source), "include_objects": True})["objects"]
    name_slot = next(
        item
        for item in objects
        if isinstance(item, dict) and item.get("locator") == "/body/p[@paraId=00100002]"
    )
    typoed_target = {
        "object_ref": name_slot["object_ref"],
        "type": "paragrapl",
        "text": name_slot.get("text", ""),
        "locator": name_slot["locator"],
    }
    batch_ref = _write_action_package(
        root,
        "work/typoed-carrier-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.dumps(typoed_target, ensure_ascii=False),
            "field_id": "author.name.zh",
            "slot_ref": _slot_ref("author.name.zh"),
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/typoed-carrier.docx",
                "idempotency_key": "reject-typoed-carrier",
            }
        )

    assert failure.value.code == "unsupported_carrier"
    assert not (root / "work/typoed-carrier.docx").exists()


def test_t3_apply_fails_closed_on_conflicts_registry_carrier_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "edit",
        lambda _args: pytest.fail("precondition failure must not call edit"),
    )

    child_ref = json.loads(
        _target_json(
            source_hash,
            object_id="obj-child",
            carrier="run",
            locator="/body/p[1]/r[1]",
            ancestor_object_ids=["obj-parent"],
        )
    )
    conflict_ref = _write_json(
        root,
        "work/conflict.json",
        {"target_refs": [child_ref]},
    )
    with pytest.raises(ToolFailure) as conflict:
        service.apply(
            {
                "candidate_hash": source_hash,
                "batch_ref": conflict_ref,
                "output_docx": "work/conflict.docx",
            }
        )
    assert conflict.value.code == "action_package_shape_retired"

    invalid_field_ref = _write_action_package(
        root,
        "work/invalid-field-action.json",
        {
            "action": "materialize_slot",
            "target_ref": _object_ref(source_hash),
            "field_id": "not.registered",
            "slot_ref": _slot_ref("not.registered"),
        },
    )
    with pytest.raises(ToolFailure) as invalid_field:
        service.apply(
            {
                "candidate_hash": source_hash,
                "batch_ref": invalid_field_ref,
                "output_docx": "work/invalid-field.docx",
            }
        )
    assert invalid_field.value.code == "phase_review_required"

    unsupported_ref = _write_action_package(
        root,
        "work/unsupported-carrier-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(_target_json(source_hash, carrier="text_box")),
        },
    )
    with pytest.raises(ToolFailure) as unsupported:
        service.apply(
            {
                "candidate_hash": source_hash,
                "batch_ref": unsupported_ref,
                "output_docx": "work/unsupported.docx",
            }
        )
    assert unsupported.value.code == "unsupported_carrier"

    with pytest.raises(ToolFailure) as path_violation:
        service.apply(
            {
                "candidate_hash": source_hash,
                "output_docx": "input/candidate.docx",
            }
        )
    assert path_violation.value.status == "error"
    assert path_violation.value.origin == "invariant"
    assert path_violation.value.code == "input_directory_read_only"


def test_t3_apply_wraps_edit_failures_in_agent_actionable_apply_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    resolved_spans = _write_phase_review(root, source_hash)
    service = DocFitToolService(task_root=root)

    def fail_edit(_args: dict[str, Any]) -> dict[str, Any]:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="existing_content_control_boundary",
            message=(
                "materialize_slot would wrap a paragraph that already contains a content control."
            ),
            suggested_actions=("Refresh target_affordance.",),
        )

    monkeypatch.setattr(service, "edit", fail_edit)
    target_ref = _target_json(source_hash, locator="/body/p[1]")
    batch_ref = _write_action_package(
        root,
        "work/wrapped-failure-action.json",
        {
            "action": "materialize_slot",
            "target_ref": json.loads(target_ref),
            "field_id": "thesis.title.zh",
            "slot_ref": resolved_spans[0]["slot_ref"],
        },
    )

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": source_hash,
                "batch_ref": batch_ref,
                "output_docx": "work/wrapped-failure.docx",
                "idempotency_key": "wrap-failure",
            }
        )

    assert failure.value.origin == "docfit_apply"
    assert failure.value.code == "existing_content_control_boundary"
    assert "docfit_apply materialize_slot failed for type=paragraph" in failure.value.message
    assert "/body/p[1]" in failure.value.message
    assert any("seven-question item 5" in item for item in failure.value.suggested_actions)
    assert any("same hash, target, action" in item for item in failure.value.suggested_actions)


def test_t3_packaged_clear_content_replaces_direct_instruction_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "edit", _fake_edit(root, seen))
    target_ref = _target_json(source_hash)
    batch_ref = _write_action_package(
        root,
        "work/empty-replacement-action.json",
        {
            "action": "clear_content",
            "target_ref": json.loads(target_ref),
        },
    )

    result = service.apply(
        {
            "schema_version": "docfit_apply_input_v1",
            "candidate_hash": source_hash,
            "batch_ref": batch_ref,
            "output_docx": "work/empty-replacement.docx",
            "idempotency_key": "empty-replacement",
        }
    )

    assert result["status"] == "ok"
    assert seen[-1]["operations"] == [
        {
            "action": "clear_content",
            "target_ref": _object_ref(source_hash),
        }
    ]


def test_t3_apply_fails_closed_on_stale_locator_bound_target_ref_after_candidate_change(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _real_task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    objects = service.inspect({"input_docx": str(_source), "include_objects": True})["objects"]
    by_locator = {
        item["locator"]: item
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("locator"), str)
    }
    remove_ref = _write_action_package(
        root,
        "work/remove-sample-action.json",
        {
            "action": "clear_content",
            "target_ref": by_locator["/body/p[@paraId=00100004]"]["object_ref"],
        },
    )
    first = service.apply(
        {
            "schema_version": "docfit_apply_input_v1",
            "candidate_hash": source_hash,
            "batch_ref": remove_ref,
            "output_docx": "work/candidate-step-1.docx",
            "idempotency_key": "remove-instruction",
        }
    )

    bind_ref = _write_action_package(
        root,
        "work/bind-name-action.json",
        {
            "action": "materialize_slot",
            "target_ref": by_locator["/body/p[@paraId=00100002]"]["object_ref"],
            "field_id": "author.name.zh",
            "slot_ref": _slot_ref("author.name.zh"),
        },
    )
    with pytest.raises(ToolFailure) as stale_target:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": first["candidate_hash"],
                "batch_ref": bind_ref,
                "output_docx": "work/candidate-step-2.docx",
                "idempotency_key": "bind-name-after-stale-ref",
            }
        )

    assert stale_target.value.code == "stale_object_ref"
    assert stale_target.value.retryable is True
    assert any(
        "current candidate document" in item for item in stale_target.value.suggested_actions
    )
    assert not (root / "work/candidate-step-2.docx").exists()
