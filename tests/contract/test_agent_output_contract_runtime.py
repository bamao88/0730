from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from docfit.app.agent_output_contract import (
    AGENT_OUTPUT_CONTRACT_SCHEMA_VERSION,
    AGENT_OUTPUT_PROOF,
    AGENT_OUTPUT_RAW_OUTPUT,
    AgentOutputContractRequest,
    agent_output_contract_feedback,
    run_agent_output_contract,
)
from docfit.app.cli import build_parser
from docfit.app.prepare_template import (
    PreparedTemplateTask,
    TemplateAgentExecution,
    _post_unit_inventory_from_checkpoint,
)
from docfit.app.settings import AgentBackend
from tests.support.source_identity import persist_source_identity, source_partition


def _tool_requests() -> tuple[dict[str, object], ...]:
    return (
        {
            "name": "mcp__docfit__docfit_evidence",
            "input": {
                "schema_version": "docfit_evidence_input_v1",
                "focus": "unit_evidence_packet",
                "unit_id": "u-cover",
            },
        },
    )


def _inventory() -> dict[str, object]:
    vocabulary = {
        "schema_version": "docfit_pre_input_field_vocabulary_v1",
        "registry": {
            "registry_id": "test.registry",
            "registry_version": "1",
            "sha256": "a" * 64,
        },
        "allowed_field_ids": ["thesis.title.zh"],
        "field_count": 1,
        "fields": [
            {
                "field_id": "thesis.title.zh",
                "label": "Chinese thesis title",
                "content_type": "text",
            }
        ],
        "digest": "b" * 64,
    }
    return {
        "document_sha256": "c" * 64,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "source_entries": [
            {
                "source_entry_id": "source-entry-cover-title",
                "text": "论文题目：玉米生长研究",
            }
        ],
        "reading_blocks": [
            {
                "block_id": "u-cover:block-0001",
                "range_id": "u-cover:range-0001",
                "unit_range_id": "u-cover:range-whole-unit",
                "text": "论文题目：玉米生长研究",
            }
        ],
    }


def _agent_output(field_id: str = "thesis.title.zh") -> dict[str, object]:
    return {
        "status": "complete",
        "summary": "Cover title semantic parts are ready for contract review.",
        "semantic_judgments": [
            {
                "source_entry_id": "source-entry-cover-title",
                "parts": [
                    {"text": "论文题目：", "role": "fixed_label"},
                    {
                        "text": "玉米生长研究",
                        "role": "fill_slot",
                        "field_id": field_id,
                    },
                ],
            }
        ],
    }


def _execution() -> TemplateAgentExecution:
    return TemplateAgentExecution(
        structured_output=_agent_output(),
        tool_uses=("Skill", "mcp__docfit__docfit_evidence"),
        skills_loaded=("docfit-school-extract",),
        session_id="agent-output-session",
        backend="test",
        num_turns=2,
        duration_ms=11,
        duration_api_ms=7,
        wall_duration_ms=13,
        sdk_query_count=1,
    )


def _backend() -> AgentBackend:
    return AgentBackend(
        name="test",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def _request(tmp_path: Path) -> AgentOutputContractRequest:
    template = tmp_path / "school.docx"
    registry = tmp_path / "field-registry.yaml"
    template.write_bytes(
        (
            Path(__file__).resolve().parents[2] / "evals/fixtures/smoke/school-template.docx"
        ).read_bytes()
    )
    registry.write_text(
        "\n".join(
            (
                "registry_id: test.registry",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: Chinese thesis title",
                "    content_type: text",
            )
        ),
        encoding="utf-8",
    )
    return AgentOutputContractRequest(
        school_template=template,
        output_directory=tmp_path / "task",
        field_registry=registry,
        resume_proof=tmp_path / "unit-boundary-checkpoint.json",
    )


def test_agent_output_contract_command_is_separate_from_prepare_template_stages() -> None:
    args = build_parser().parse_args(
        [
            "agent-output-contract",
            "--school-template",
            "school.docx",
            "--field-registry",
            "field-registry.yaml",
            "--output",
            "task",
            "--resume-proof",
            "work/.docfit/unit-boundary-checkpoint.json",
        ]
    )

    assert args.command == "agent-output-contract"
    assert args.resume_proof == "work/.docfit/unit-boundary-checkpoint.json"


def test_agent_output_contract_feedback_requires_real_unit_packet_tool_use() -> None:
    feedback = agent_output_contract_feedback(
        structured_output=_agent_output(),
        inventory=_inventory(),
        tool_requests=(),
    )

    assert feedback is not None
    assert feedback["status"] == "needs_input"
    assert feedback["blockers"][0]["code"] == "agent_output_unit_packet_not_observed"


def test_agent_output_contract_feedback_rejects_agent_created_field_id() -> None:
    feedback = agent_output_contract_feedback(
        structured_output=_agent_output(field_id="thesis.subtitle.zh"),
        inventory=_inventory(),
        tool_requests=_tool_requests(),
    )

    assert feedback is not None
    assert feedback["status"] == "needs_input"
    assert {item["code"] for item in feedback["blockers"] if isinstance(item, dict)} == {
        "field_id_not_in_input_vocabulary"
    }


def test_p0_n06_agent_output_contract_rejects_legacy_reading_scope() -> None:
    output = _agent_output()
    judgment = output["semantic_judgments"][0]
    assert isinstance(judgment, dict)
    judgment.pop("source_entry_id")
    judgment["scope"] = {"reading_block_id": "u-cover:block-0001"}

    feedback = agent_output_contract_feedback(
        structured_output=output,
        inventory=_inventory(),
        tool_requests=_tool_requests(),
    )

    assert feedback is not None
    assert feedback["status"] == "needs_input"
    assert feedback["blockers"][0]["code"] == "legacy_reading_scope_unsupported"


def test_agent_output_contract_run_writes_raw_agent_output_without_later_stages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    expected_output = {}

    async def fake_unit_boundary_checkpoint(
        *,
        prepared: PreparedTemplateTask,
        request: AgentOutputContractRequest,
    ) -> dict[str, object]:
        initial = json.loads(
            (prepared.task_root / "work/.docfit/initial-source-inventory.json").read_text()
        )
        inventory = {
            "document_sha256": prepared.template_sha256,
            "canonical_source_inventory": initial["canonical_source_inventory"],
        }
        proof = source_partition(inventory, unit_id="u-cover", unit_name="封面")
        persist_source_identity(prepared.task_root, inventory, objects=initial["objects"])
        return proof

    async def fake_agent_output_only(
        *,
        prepared: PreparedTemplateTask,
        backend: AgentBackend,
        config_directory: Path,
        unit_boundary_checkpoint: dict[str, object],
    ) -> tuple[TemplateAgentExecution, tuple[dict[str, object], ...]]:
        inventory = _post_unit_inventory_from_checkpoint(prepared, unit_boundary_checkpoint)
        expected_output.update(
            {
                "status": "complete",
                "summary": "Source semantics ready.",
                "semantic_judgments": [
                    {
                        "source_entry_id": entry["source_entry_id"],
                        "parts": [{"text": entry["text"], "role": "fixed_label"}],
                    }
                    for entry in inventory["source_entries"]
                ],
            }
        )
        return replace(_execution(), structured_output=expected_output), _tool_requests()

    monkeypatch.setattr(
        "docfit.app.agent_output_contract._unit_boundary_checkpoint_for_request",
        fake_unit_boundary_checkpoint,
    )
    monkeypatch.setattr(
        "docfit.app.agent_output_contract.iter_agent_backends",
        lambda: (_backend(),),
    )
    monkeypatch.setattr(
        "docfit.app.agent_output_contract._run_agent_output_only",
        fake_agent_output_only,
    )

    report = asyncio.run(run_agent_output_contract(_request(tmp_path)))

    task_root = Path(report.task_root)
    proof = json.loads((task_root / AGENT_OUTPUT_PROOF).read_text(encoding="utf-8"))
    raw_output = json.loads((task_root / AGENT_OUTPUT_RAW_OUTPUT).read_text(encoding="utf-8"))

    assert report.status == "checkpointed"
    assert proof["schema_version"] == AGENT_OUTPUT_CONTRACT_SCHEMA_VERSION
    assert proof["checkpoint"] == "agent-output"
    assert proof["status"] == "ok"
    assert proof["checks"][-3:] == [
        {"name": "harness_mapping_not_run", "result": "not_run"},
        {"name": "word_materialization_not_run", "result": "not_run"},
        {"name": "publication_not_run", "result": "not_run"},
    ]
    assert raw_output == expected_output
    assert not (task_root / "work/.docfit/post-unit-checkpoint.json").exists()
    assert not (task_root / "work/.docfit/post-unit-materialization").exists()
    assert not (task_root / "output/final-template.docx").exists()
    assert not (task_root / "output/fill-contract.yaml").exists()
