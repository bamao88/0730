from __future__ import annotations

import inspect
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import publish_template_artifact
from docfit.template.judgment_shape import validate_ordered_semantic_parts
from docfit.template.materialization import (
    compile_materialization_intents,
    materialization_readiness_feedback,
)
from docfit.template.materialization.handlers.slots import materialize_slot_paragraph_parts
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from docfit.tools.service import DocFitToolService
from docfit.tools.surface import (
    DOCFIT_EVIDENCE_SCHEMA,
    EVIDENCE_FOCUS,
    TEMPLATE_SEMANTIC_EVIDENCE_FOCUS,
)
from tests.support.source_identity import persist_source_identity, source_partition

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
BLOCK_ID = "u:block-0001"
SPAN_REF = f"reading_block_id={BLOCK_ID};part_index=0"
SLOT_REF = f"{SPAN_REF};field_id=thesis.title.zh"


def _registry(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "field-registry.yaml"
    path.write_text(
        "\n".join(
            (
                "registry_id: test.registry",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: Title",
                "    content_type: text",
                "  - field_id: advisor.name.zh",
                "    label: Advisor",
                "    content_type: text",
                "  - field_id: generated.toc",
                "    label: TOC",
                "    content_type: section",
                "    value_sources:",
                "      - system_generated",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _span(*, field_id: str | None = "thesis.title.zh") -> dict[str, object]:
    span: dict[str, object] = {
        "span_ref": SPAN_REF,
        "scope": {"reading_block_id": BLOCK_ID},
        "reading_block_id": BLOCK_ID,
        "part_index": 0,
        "role": "fill_slot",
        "text": "x",
        "covered_object_ids": ["obj-slot"],
    }
    if field_id is not None:
        span["field_id"] = field_id
        span["slot_ref"] = f"{SPAN_REF};field_id={field_id}"
    return span


def _inventory(
    vocabulary: dict[str, object],
    *,
    source_hash: str = "a" * 64,
) -> dict[str, object]:
    return {
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "objects": [{"object_id": "obj-slot", "type": "run", "locator": "/body/p[1]/r[1]"}],
        "reading_blocks": [
            {
                "block_id": BLOCK_ID,
                "range_id": "u:range-0001",
                "unit_id": "u",
                "text": "x",
                "covered_object_ids": ["obj-slot"],
                "object_text_spans": [{"object_id": "obj-slot"}],
            }
        ],
    }


def _review(
    vocabulary: dict[str, object],
    judgments: list[dict[str, object]],
    *,
    source_hash: str = "a" * 64,
) -> dict[str, object]:
    return {
        "document_sha256": source_hash,
        "semantic_judgments": judgments,
        "semantic_judgments_sha256": sha256_json(judgments),
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }


def _slot_judgment(*, field_id: str = "thesis.title.zh") -> dict[str, object]:
    return {
        "scope": {"reading_block_id": BLOCK_ID},
        "parts": [{"text": "x", "role": "fill_slot", "field_id": field_id}],
        "resolved_spans": [_span(field_id=field_id)],
    }


def _codes(feedback: dict[str, object]) -> list[str]:
    blockers = feedback.get("blockers")
    assert isinstance(blockers, list)
    return [str(item["code"]) for item in blockers if isinstance(item, dict)]


def test_field_id_vocabulary_is_the_only_positive_field_source(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    vocabulary = registry.pre_input_vocabulary(allowed_field_ids=("advisor.name.zh",))
    review = _review(vocabulary, [_slot_judgment(field_id="thesis.title.zh")])

    compiled = compile_materialization_intents(review=review, registry=registry)
    readiness = materialization_readiness_feedback(
        inventory=_inventory(vocabulary),
        review=review,
        registry=registry,
    )

    assert compiled.ready is False
    assert compiled.intents == ()
    assert compiled.unsupported[0].reason_code == "materialization_field_not_in_vocabulary"
    assert readiness is not None
    assert _codes(readiness) == ["materialization_field_not_in_vocabulary"]


@pytest.mark.parametrize(
    "legacy_patch",
    (
        {"registry_field": "thesis.title.zh"},
        {"semantic_field": "title"},
        {"bound_field_id": "thesis.title.zh"},
        {"bound_field_ids": ["thesis.title.zh"]},
        {"required_field_ids": ["thesis.title.zh"]},
        {"generated_field_id": "generated.toc"},
    ),
)
def test_legacy_aliases_are_denylisted_not_migrated(
    tmp_path: Path,
    legacy_patch: dict[str, object],
) -> None:
    registry = _registry(tmp_path)
    vocabulary = registry.pre_input_vocabulary()
    judgments = [
        {
            "source_entry_id": "source-entry-title",
            "parts": [{"text": "x", "role": "fill_slot", **legacy_patch}],
            "resolved_spans": [_span()],
        }
    ]

    shape = validate_ordered_semantic_parts(
        [{key: value for key, value in judgments[0].items() if key != "resolved_spans"}],
        allowed_field_ids=vocabulary["allowed_field_ids"],
        source_entry_ids=["source-entry-title"],
    )
    compiled = compile_materialization_intents(
        review=_review(vocabulary, judgments),
        registry=registry,
    )

    assert shape["status"] == "needs_input"
    assert "agent_authored_legacy_or_internal_id" in _codes(shape)
    assert compiled.ready is False
    assert compiled.intents == ()
    assert compiled.unsupported[0].reason_code == "materialization_legacy_shape_unsupported"


def test_runtime_registry_search_cannot_return_agent_field_choices(tmp_path: Path) -> None:
    service = DocFitToolService(task_root=tmp_path)

    assert "registry_field" not in EVIDENCE_FOCUS
    assert "registry_field" not in TEMPLATE_SEMANTIC_EVIDENCE_FOCUS
    assert "field_id" not in DOCFIT_EVIDENCE_SCHEMA["properties"]
    assert "semantic_field" not in DOCFIT_EVIDENCE_SCHEMA["properties"]

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"focus": "registry_field", "semantic_field": "title"})

    assert caught.value.code == "registry_field_runtime_removed"
    assert "field_id_vocabulary.allowed_field_ids" in " ".join(caught.value.suggested_actions)


def test_materializer_does_not_backfill_part_field_id_from_span_or_registry(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    paragraph = ET.Element(f"{W}p")
    run = ET.SubElement(paragraph, f"{W}r")
    text = ET.SubElement(run, f"{W}t")
    text.text = "x"

    with pytest.raises(ToolFailure) as caught:
        kwargs = {
            "paragraph": paragraph,
            "block_id": BLOCK_ID,
            "resolved_spans": [_span(field_id="thesis.title.zh")],
            "registry": registry,
            "properties": None,
        }
        if (
            "indexed_ordered_parts"
            in inspect.signature(materialize_slot_paragraph_parts).parameters
        ):
            kwargs["indexed_ordered_parts"] = [
                (
                    0,
                    {
                        "text": "x",
                        "role": "fill_slot",
                        "registry_field": "thesis.title.zh",
                    },
                )
            ]
        else:
            kwargs["ordered_parts"] = [
                {"text": "x", "role": "fill_slot", "registry_field": "thesis.title.zh"}
            ]
        materialize_slot_paragraph_parts(
            **kwargs,
        )

    assert caught.value.code == "materialization_slot_ref_missing"


def test_publication_and_fill_contract_do_not_backfill_from_word_or_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Isolate the field/provenance contract; visual publication gates are tested separately.
    monkeypatch.setattr(
        "docfit.template.artifact.validate_final_visual_review", lambda *args, **kwargs: None
    )
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    source.parent.mkdir(parents=True)
    candidate.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    candidate.write_bytes(b"candidate")
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    registry = _registry(root)
    vocabulary = registry.pre_input_vocabulary()
    judgments = [
        {
            "scope": {"reading_block_id": BLOCK_ID},
            "parts": [{"text": "x", "role": "fill_slot", "registry_field": "thesis.title.zh"}],
            "resolved_spans": [_span(field_id="thesis.title.zh")],
        }
    ]
    _write_publication_inputs(
        root=root,
        registry=registry,
        source_hash=source_hash,
        vocabulary=vocabulary,
        judgments=judgments,
    )
    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry.path,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code in {
        "template_slot_semantics_invalid",
        "published_slot_part_mismatch",
    }
    assert not (root / "output/fill-contract.yaml").exists()


def test_contract_limits_retired_paths_to_negative_or_historical_uses() -> None:
    contract = (
        Path(__file__).resolve().parents[2] / "docs/contracts/template-extraction.md"
    ).read_text(encoding="utf-8")
    section = contract.split("核心字段 ID 合同闭环只证明", 1)[1].split(
        "post-unit 的 `semantic_judgments[]`", 1
    )[0]

    assert "不证明 Agent 在真实学校模板里语义选对" in section
    assert "唯一合法来源" in section
    assert "不能作为正向输入被兼容迁移" in section
    assert "runtime Registry search 不向 Agent 返回可选字段" in section
    assert "都不能从 Registry lookup" in section
    assert "fail-closed 实现、denylist、负向测试或历史/说明文档" in section


def _write_publication_inputs(
    *,
    root: Path,
    registry: FieldRegistrySnapshot,
    source_hash: str,
    vocabulary: dict[str, object],
    judgments: list[dict[str, object]],
) -> None:
    harness = root / "work/.docfit/harness"
    materialization_dir = root / "work/.docfit/post-unit-materialization"
    harness.mkdir(parents=True, exist_ok=True)
    materialization_dir.mkdir(parents=True, exist_ok=True)
    inventory = _inventory(vocabulary, source_hash=source_hash)
    inventory["source_entries"] = [
        {
            "source_entry_id": "source-entry-title",
            "text": "x",
            "entry_type": "text",
            "source_order": {"block": 1, "inline": 0},
            "provenance": [
                {
                    "object_id": "obj-slot",
                    "locator": "/body/p[1]/r[1]",
                    "text_span": [0, 1],
                }
            ],
        }
    ]
    source_partition(inventory)
    persist_source_identity(root, inventory)
    (harness / "object-inventory.json").write_text(
        json.dumps(inventory),
        encoding="utf-8",
    )
    semantic_digest = sha256_json(judgments)
    (harness / "semantic-judgments.json").write_text(
        json.dumps(_review(vocabulary, judgments, source_hash=source_hash)),
        encoding="utf-8",
    )
    (materialization_dir / "materialization.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "semantic_judgments_sha256": semantic_digest,
                "field_vocabulary_digest": vocabulary["digest"],
                "field_registry_ref": registry.identity(),
                "operations": [
                    {
                        "action": "materialize_slot",
                        "field_id": "thesis.title.zh",
                        "span_ref": SPAN_REF,
                        "slot_ref": SLOT_REF,
                    }
                ],
                "mutation_receipts": [
                    {
                        "field_ids": ["thesis.title.zh"],
                        "span_refs": [SPAN_REF],
                        "slot_refs": [SLOT_REF],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class _FakeOffice:
    def validate_snapshot(self, _document: Path) -> dict[str, object]:
        return {"detail": "ok"}
