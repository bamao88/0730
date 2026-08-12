from __future__ import annotations

import asyncio
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from docfit.app.settings import AgentBackend, BackendName
from docfit.app.student_content_fill import (
    PreparedStudentContentExtraction,
    StudentExtractionExecution,
    _run_batched_student_extraction,
    run_student_extraction_agent,
)
from docfit.content.extraction import extraction_output_schema, validate_extraction
from docfit.content.student import build_student_inventory
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.observability.transcript import SDKTranscriptManager
from docfit.tools.inspection import InspectedObject, Inspection
from docfit.tools.runtime import ToolFailure


def _object(object_id: str, locator: str, text: str) -> InspectedObject:
    kind = "picture" if "drawing" in locator else "table" if "/tbl[" in locator else "paragraph"
    return InspectedObject(
        locator,
        kind,
        text,
        "Normal",
        {},
        {
            "document_sha256": "a" * 64,
            "object_id": object_id,
            "expected_fingerprint": object_id,
        },
    )


def _inspection() -> Inspection:
    paragraph = "/body/p[@paraId=00000002]"
    return Inspection(
        "a" * 64,
        (
            _object("obj-title", "/body/p[@paraId=00000001]", "A verified title"),
            _object("obj-body-1", paragraph, "1 Introduction"),
            _object("obj-picture", f"{paragraph}/r[2]/drawing[1]", ""),
            _object("obj-body-2", "/body/p[@paraId=00000003]", "Body text"),
            _object("obj-ref", "/body/p[@paraId=00000004]", "Reference entry"),
        ),
        {"paragraphs": 4, "images": 1},
        (),
        (),
        {},
    )


def _registry(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "registry.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.1.0",
                "fields": [
                    {
                        "field_id": "thesis.title.en",
                        "label": "English title",
                        "meaning": "The thesis title in English.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.heading.level1",
                        "label": "Chapter heading",
                        "meaning": "A first-level body heading.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.heading.level2",
                        "label": "Section heading",
                        "meaning": "A second-level body heading.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.heading.level3",
                        "label": "Subsection heading",
                        "meaning": "A third-level body heading.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.paragraph",
                        "label": "Body paragraph",
                        "meaning": "A paragraph in the thesis body.",
                        "content_type": "rich_text",
                    },
                    {
                        "field_id": "body.figure",
                        "label": "Figure",
                        "meaning": "An image in the thesis body.",
                        "content_type": "image",
                    },
                    {
                        "field_id": "body.figure.caption",
                        "label": "Figure caption",
                        "meaning": "A caption belonging to a figure.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.table",
                        "label": "Table",
                        "meaning": "A table in the thesis body.",
                        "content_type": "table",
                    },
                    {
                        "field_id": "body.table.caption",
                        "label": "Table caption",
                        "meaning": "A caption belonging to a table.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "references.entries",
                        "label": "Reference entry",
                        "meaning": "One entry in the reference list.",
                        "content_type": "rich_text",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def test_source_inventory_builds_ordered_neutral_content_before_semantics() -> None:
    inventory = build_student_inventory(_inspection())

    assert inventory["schema_version"] == "docfit-student-source-inventory/v2"
    assert [
        (item["physical_type"], item["source_order"])
        for item in inventory["content_items"]
    ] == [
        ("text", {"block": 1, "inline": 0}),
        ("image", {"block": 2, "inline": 0}),
        ("text", {"block": 2, "inline": 1}),
        ("text", {"block": 3, "inline": 0}),
        ("text", {"block": 4, "inline": 0}),
    ]
    assert all("field_id" not in item for item in inventory["content_items"])
    picture = inventory["content_items"][1]
    assert picture["source_object_ids"] == ["obj-picture"]
    assert picture["transport_source_object_id"] == "obj-body-1"
    assert inventory["content_items"][2]["source_facts"]["numbering_shape"] == (
        "decimal_1_component"
    )


def test_source_inventory_places_floating_drawing_before_host_text(
    tmp_path: Path,
) -> None:
    source = tmp_path / "student.docx"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
  <w:body>
    <w:p w14:paraId="00000001">
      <w:r><w:t>Figure caption</w:t></w:r>
      <w:r><w:drawing/></w:r>
    </w:p>
  </w:body>
</w:document>
""",
        )
    paragraph = "/body/p[@paraId=00000001]"
    inspection = Inspection(
        "a" * 64,
        (
            _object("obj-caption", paragraph, "Figure caption"),
            _object("obj-picture", f"{paragraph}/r[1]/drawing[1]", ""),
        ),
        {"paragraphs": 1, "images": 1},
        (),
        (),
        {},
    )

    inventory = build_student_inventory(inspection, source_docx=source)

    assert [
        (item["physical_type"], item["source_object_ids"], item["source_order"])
        for item in inventory["content_items"]
    ] == [
        ("image", ["obj-picture"], {"block": 1, "inline": 0}),
        ("text", ["obj-caption"], {"block": 1, "inline": 1}),
    ]


def test_source_inventory_prefers_explicit_ooxml_equation_fact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "student.docx"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
  xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
  <w:body>
    <w:p w14:paraId="00000001">
      <m:oMath><m:r><m:t>x=1</m:t></m:r></m:oMath>
    </w:p>
  </w:body>
</w:document>
""",
        )
    inspection = Inspection(
        "a" * 64,
        (_object("obj-equation", "/body/p[@paraId=00000001]", "x=1"),),
        {"paragraphs": 1, "equations": 1},
        (),
        (),
        {},
    )

    inventory = build_student_inventory(inspection, source_docx=source)

    assert inventory["content_item_count"] == 1
    assert inventory["content_items"][0]["physical_type"] == "equation"
    assert inventory["content_items"][0]["source_object_ids"] == ["obj-equation"]


def test_agent_schema_can_only_annotate_existing_content_items(tmp_path: Path) -> None:
    inventory = build_student_inventory(_inspection())
    schema = extraction_output_schema(inventory, _registry(tmp_path))

    assert schema["properties"]["schema_version"] == {"const": 3}
    annotations = schema["properties"]["annotations"]
    assert annotations["minItems"] == len(inventory["content_items"])
    assert annotations["items"]["properties"]["source_content_id"]["enum"] == [
        item["source_content_id"] for item in inventory["content_items"]
    ]
    rendered = str(annotations)
    assert "source_order" not in rendered
    assert "body_sequence" not in rendered
    assert "value" not in annotations["items"]["properties"]


def test_postprocessing_preserves_source_order_and_derives_field_results(
    tmp_path: Path,
) -> None:
    inventory = build_student_inventory(_inspection())
    ids = [item["source_content_id"] for item in inventory["content_items"]]
    payload = {
        "schema_version": 3,
        "annotations": [
            _annotation(ids[0], "thesis.title.en"),
            _annotation(ids[1], "body.figure"),
            _annotation(ids[2], "body.heading.level1"),
            _annotation(ids[3], "body.paragraph"),
            _annotation(ids[4], "references.entries"),
        ],
        "relations": [],
        "summary": "Synthetic semantic annotations.",
        "uncertainties": [],
    }

    model = validate_extraction(
        payload,
        inventory=inventory,
        registry=_registry(tmp_path),
    )

    assert model["schema_version"] == "docfit-student-content-model/v2"
    assert model["status"] == "READY"
    assert [item["source_order"] for item in model["items"]] == [
        item["source_order"] for item in inventory["content_items"]
    ]
    assert [item["field_id"] for item in model["items"]] == [
        "thesis.title.en",
        "body.figure",
        "body.heading.level1",
        "body.paragraph",
        "references.entries",
    ]
    results = {item["field_id"]: item for item in model["field_results"]}
    assert results["body.figure"]["item_count"] == 1
    assert set(results) == {
        "thesis.title.en",
        "body.heading.level1",
        "body.figure",
        "body.paragraph",
        "references.entries",
    }
    assert model["source_coverage"]["all_source_objects_accounted_for"] is True


def test_postprocessing_normalizes_only_isolated_numbered_heading_outlier(
    tmp_path: Path,
) -> None:
    inspection = Inspection(
        "a" * 64,
        (
            _object("obj-section", "/body/p[@paraId=00000001]", "1 Section"),
            _object("obj-sub-1", "/body/p[@paraId=00000002]", "1.1 First"),
            _object("obj-sub-2", "/body/p[@paraId=00000003]", "1.2 Second"),
            _object("obj-sub-3", "/body/p[@paraId=00000004]", "1.3 Third"),
            _object("obj-sub-4", "/body/p[@paraId=00000005]", "1.4 Fourth"),
            _object("obj-sub-5", "/body/p[@paraId=00000006]", "1.5 Fifth"),
        ),
        {"paragraphs": 6},
        (),
        (),
        {},
    )
    inventory = build_student_inventory(inspection)
    ids = [item["source_content_id"] for item in inventory["content_items"]]
    payload = {
        "schema_version": 3,
        "annotations": [
            _annotation(ids[0], "body.heading.level2"),
            _annotation(ids[1], "body.heading.level3"),
            _annotation(ids[2], "body.heading.level2"),
            _annotation(ids[3], "body.heading.level3"),
            _annotation(ids[4], "body.heading.level3"),
            _annotation(ids[5], "body.heading.level3"),
        ],
        "relations": [],
        "summary": "Synthetic semantic annotations.",
        "uncertainties": [],
    }

    model = validate_extraction(
        payload,
        inventory=inventory,
        registry=_registry(tmp_path),
    )

    assert [item["field_id"] for item in model["items"]] == [
        "body.heading.level2",
        "body.heading.level3",
        "body.heading.level3",
        "body.heading.level3",
        "body.heading.level3",
        "body.heading.level3",
    ]
    section_id = model["items"][0]["content_id"]
    assert all(
        item["parent_content_id"] == section_id for item in model["items"][1:]
    )


def test_postprocessing_materializes_all_consecutive_figure_caption_relations(
    tmp_path: Path,
) -> None:
    host = "/body/p[@paraId=00000001]"
    inspection = Inspection(
        "a" * 64,
        (
            _object("obj-figure", f"{host}/r[1]/drawing[1]", ""),
            _object("obj-caption-1", host, "Figure 1 Caption"),
            _object(
                "obj-caption-2",
                "/body/p[@paraId=00000002]",
                "图 1 题注",
            ),
        ),
        {"paragraphs": 2, "images": 1},
        (),
        (),
        {},
    )
    inventory = build_student_inventory(inspection)
    ids = [item["source_content_id"] for item in inventory["content_items"]]
    payload = {
        "schema_version": 3,
        "annotations": [
            _annotation(ids[0], "body.figure"),
            _annotation(ids[1], "body.figure.caption"),
            _annotation(ids[2], "body.figure.caption"),
        ],
        "relations": [
            {
                "relation_type": "caption_of",
                "source_content_id": ids[1],
                "target_content_id": ids[0],
                "confidence": 0.8,
                "note": "Agent-proposed relation.",
            }
        ],
        "summary": "Synthetic semantic annotations.",
        "uncertainties": [],
    }

    model = validate_extraction(
        payload,
        inventory=inventory,
        registry=_registry(tmp_path),
    )

    assert [
        (relation["source_content_id"], relation["target_content_id"])
        for relation in model["relations"]
        if relation["relation_type"] == "caption_of"
    ] == [
        (model["items"][1]["content_id"], model["items"][0]["content_id"]),
        (model["items"][2]["content_id"], model["items"][0]["content_id"]),
    ]


def test_postprocessing_binds_a_preceding_table_caption_by_typed_adjacency(
    tmp_path: Path,
) -> None:
    inspection = Inspection(
        "a" * 64,
        (
            _object(
                "obj-table-caption",
                "/body/p[@paraId=00000001]",
                "Table 1 Caption",
            ),
            _object("obj-table", "/body/tbl[1]", "Cell value"),
        ),
        {"paragraphs": 1, "tables": 1},
        (),
        (),
        {},
    )
    inventory = build_student_inventory(inspection)
    ids = [item["source_content_id"] for item in inventory["content_items"]]
    payload = {
        "schema_version": 3,
        "annotations": [
            _annotation(ids[0], "body.table.caption"),
            _annotation(ids[1], "body.table"),
        ],
        "relations": [],
        "summary": "Synthetic semantic annotations.",
        "uncertainties": [],
    }

    model = validate_extraction(
        payload,
        inventory=inventory,
        registry=_registry(tmp_path),
    )

    assert model["relations"] == [
        {
            "relation_type": "caption_of",
            "source_content_id": model["items"][0]["content_id"],
            "target_content_id": model["items"][1]["content_id"],
            "confidence": 1.0,
            "note": "Deterministic typed-caption adjacency binding.",
        }
    ]


def test_postprocessing_rejects_agent_attempt_to_omit_content(tmp_path: Path) -> None:
    inventory = build_student_inventory(_inspection())
    first = inventory["content_items"][0]["source_content_id"]
    payload = {
        "schema_version": 3,
        "annotations": [
            _annotation(first, "thesis.title.en")
        ],
        "relations": [],
        "summary": "Incomplete.",
        "uncertainties": [],
    }

    with pytest.raises(ToolFailure) as captured:
        validate_extraction(payload, inventory=inventory, registry=_registry(tmp_path))

    assert captured.value.code == "student_content_annotation_keys_invalid"


def test_batching_is_execution_only_and_merges_every_source_item_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = build_student_inventory(_inspection())
    registry = _registry(tmp_path)
    monkeypatch.setattr(
        "docfit.app.student_content_fill.STUDENT_EXTRACTION_BATCH_SIZE",
        2,
    )
    prepared = PreparedStudentContentExtraction(
        task_root=tmp_path,
        source_docx=tmp_path / "student.docx",
        field_registry=registry.path,
        inventory_path=tmp_path / "student-inventory.json",
        source_sha256=str(inventory["source_sha256"]),
        registry_sha256=registry.sha256,
        inventory=inventory,
    )
    by_id = {
        item["source_content_id"]: item for item in inventory["content_items"]
    }

    async def runner(prompt, batch, schema, transcripts):
        del prompt, transcripts
        assert batch.batch is not None
        primary_ids = batch.batch["primary_content_ids"]
        assert schema["properties"]["annotations"]["minItems"] == len(primary_ids)
        annotations = []
        for source_content_id in primary_ids:
            item = by_id[source_content_id]
            field_id = {
                "obj-title": "thesis.title.en",
                "obj-body-1": "body.heading.level1",
                "obj-picture": "body.figure",
                "obj-body-2": "body.paragraph",
                "obj-ref": "references.entries",
            }[item["source_object_ids"][0]]
            annotations.append(
                {
                    "source_content_id": source_content_id,
                    "classification_status": "classified",
                    "field_id": field_id,
                    "confidence": 1.0,
                    "note": "Synthetic batch annotation.",
                }
            )
        return StudentExtractionExecution(
            structured_output={
                "schema_version": 3,
                "annotations": annotations,
                "relations": [],
                "summary": "Synthetic batch.",
                "uncertainties": [],
            },
            backend="synthetic",
            session_id=f"batch-{batch.batch['index']}",
            tool_uses=(),
            skills_loaded=(),
        )

    execution = asyncio.run(
        _run_batched_student_extraction(
            prepared=prepared,
            runner=runner,
            transcripts=object(),  # type: ignore[arg-type]
        )
    )
    model = validate_extraction(
        execution.structured_output,
        inventory=inventory,
        registry=registry,
    )

    assert len(execution.batch_evidence) == 3
    assert [item["source_order"] for item in model["items"]] == [
        item["source_order"] for item in inventory["content_items"]
    ]
    assert model["status"] == "READY"


def _backend(name: BackendName, candidate: str = "primary") -> AgentBackend:
    return AgentBackend(
        name=name,
        base_url=f"https://{name}.example/",
        model=f"{name}-model",
        credential_variable=f"DOCFIT_{name.upper()}_API_KEY_{candidate.upper()}",
        api_key=f"{name}-{candidate}-secret",
    )


def test_live_runner_retries_retryable_structured_output_miss_on_same_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend("minimax")
    calls: list[str] = []

    async def fake_run_backend(
        prompt: str,
        prepared: PreparedStudentContentExtraction,
        schema: dict[str, object],
        candidate: AgentBackend,
        config_directory: Path,
    ) -> StudentExtractionExecution:
        del prepared, schema
        assert prompt == "prompt"
        assert config_directory.is_dir()
        calls.append(candidate.credential_variable)
        if len(calls) == 1:
            raise ToolFailure(
                status="error",
                origin="engine",
                code="student_extraction_agent_structured_output_missing",
                message="transient structured output miss",
                retryable=True,
            )
        return StudentExtractionExecution(
            structured_output={"schema_version": 3},
            backend=candidate.name,
            session_id="live-session",
            tool_uses=("StructuredOutput",),
            skills_loaded=(),
        )

    monkeypatch.setattr(
        "docfit.app.student_content_fill.iter_agent_backends",
        lambda: iter((backend,)),
    )
    monkeypatch.setattr(
        "docfit.app.student_content_fill._run_extraction_backend",
        fake_run_backend,
    )
    result = asyncio.run(
        run_student_extraction_agent(
            "prompt",
            object(),  # type: ignore[arg-type]
            {},
            SDKTranscriptManager(parent=tmp_path / "transcripts"),
        )
    )

    assert result.backend == "minimax"
    assert calls == [
        "DOCFIT_MINIMAX_API_KEY_PRIMARY",
        "DOCFIT_MINIMAX_API_KEY_PRIMARY",
    ]


def test_live_runner_rotates_credential_after_nonretryable_backend_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = (_backend("kimi", "first"), _backend("kimi", "backup"))
    calls: list[str] = []

    async def fake_run_backend(
        prompt: str,
        prepared: PreparedStudentContentExtraction,
        schema: dict[str, object],
        candidate: AgentBackend,
        config_directory: Path,
    ) -> StudentExtractionExecution:
        del prompt, prepared, schema
        assert config_directory.is_dir()
        calls.append(candidate.credential_variable)
        if candidate.credential_variable.endswith("FIRST"):
            raise ToolFailure(
                status="error",
                origin="engine",
                code="student_extraction_agent_backend_error",
                message="HTTP 403",
                retryable=False,
            )
        return StudentExtractionExecution(
            structured_output={"schema_version": 3},
            backend=candidate.name,
            session_id="backup-live-session",
            tool_uses=("StructuredOutput",),
            skills_loaded=(),
        )

    monkeypatch.setattr(
        "docfit.app.student_content_fill.iter_agent_backends",
        lambda: iter(backends),
    )
    monkeypatch.setattr(
        "docfit.app.student_content_fill._run_extraction_backend",
        fake_run_backend,
    )
    result = asyncio.run(
        run_student_extraction_agent(
            "prompt",
            object(),  # type: ignore[arg-type]
            {},
            SDKTranscriptManager(parent=tmp_path / "transcripts"),
        )
    )

    assert result.session_id == "backup-live-session"
    assert calls == ["DOCFIT_KIMI_API_KEY_FIRST", "DOCFIT_KIMI_API_KEY_BACKUP"]


def _annotation(
    source_content_id: str,
    field_id: str,
) -> dict[str, object]:
    return {
        "source_content_id": source_content_id,
        "classification_status": "classified",
        "field_id": field_id,
        "confidence": 1.0,
        "note": "Synthetic exact classification.",
    }
