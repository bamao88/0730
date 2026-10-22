from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


CURRENT_ENTRYPOINTS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "ARCHITECTURE.md",
    ROOT / "STATUS.md",
    ROOT / "docs/README.md",
    ROOT / "docs/docfit-00-index.md",
    ROOT / "docs/docfit-01-architecture-core.md",
    ROOT / "docs/docfit-02-testing-and-iteration.md",
    ROOT / "docs/adr/README.md",
    ROOT / "docs/contracts/template-extraction.md",
    ROOT / "docs/human/README.md",
    ROOT / "docs/modules/README.md",
    ROOT / "docs/modules/final-word-generation.md",
    ROOT / "docs/modules/student-content-extraction.md",
    ROOT / "docs/modules/template-extraction.md",
    ROOT / "docs/plans/README.md",
    ROOT / "docs/status/active/docfit-school-extract-v2.md",
    ROOT / ".claude/skills/docfit-school-extract/SKILL.md",
    ROOT / "memory/README.md",
    ROOT / "tests/README.md",
    ROOT / "tests/manual-diagnostics/README.md",
]


REMOVED_AUTHORITY_PATHS = [
    "docfit-agent-first-template-architecture.md",
    "docfit-04-skills-design.md",
    "docfit-05-tools-and-data-design.md",
    "docfit-06-development-roadmap.md",
]


REMOVED_DOCUMENT_PATHS = [
    *(f"docs/{path}" for path in REMOVED_AUTHORITY_PATHS),
    "docs/plans/docfit-body-template-extraction-spec.md",
    "docs/plans/docfit-development-plan.md",
    "docs/plans/docfit-knowledge-package-v1.md",
    "docs/plans/docfit-m1-tools-v1.md",
    "docs/plans/docfit-o0-local-observability.md",
    "docs/plans/docfit-progressive-subagents.md",
    "docs/plans/docfit-school-extract-core-problem-classes.md",
    "docs/plans/docfit-student-content-placement-debug.md",
    "docs/plans/docfit-template-tool-v5.md",
    "docs/plans/docfit-unit-boundary-tool-poc.md",
    "docs/status/active/docfit-development-plan.md",
    "docs/status/active/docfit-knowledge-package-v1.md",
    "docs/status/active/docfit-m0.md",
    "docs/status/active/docfit-progressive-subagents.md",
    "docs/status/active/docfit-template-tool-v5.md",
]


STALE_CURRENT_ASSERTIONS = [
    "当前单一架构权威",
    "唯一五个稳定",
    "五个稳定 `docx_*` Tool",
]


def test_removed_architecture_docs_stay_removed() -> None:
    for relative_path in REMOVED_DOCUMENT_PATHS:
        assert not (ROOT / relative_path).exists()


def test_current_entrypoints_do_not_reference_removed_authorities() -> None:
    for path in CURRENT_ENTRYPOINTS:
        text = path.read_text(encoding="utf-8")
        for removed in REMOVED_AUTHORITY_PATHS:
            assert removed not in text, f"{path} references removed authority {removed}"


def test_current_entrypoints_do_not_reintroduce_stale_tool_count_contracts() -> None:
    for path in CURRENT_ENTRYPOINTS:
        text = path.read_text(encoding="utf-8")
        for phrase in STALE_CURRENT_ASSERTIONS:
            assert phrase not in text, f"{path} reintroduces stale assertion {phrase!r}"


def test_active_template_status_tracks_current_post_unit_boundary() -> None:
    status = (ROOT / "docs/status/active/docfit-school-extract-v2.md").read_text(
        encoding="utf-8"
    )

    assert "scoped_closure_v1` / `coverage_closure` 对象覆盖协议已退役" in status
    assert "post-unit Agent-visible Tool surface 只保留 `docfit_evidence`" in status
    old_tool_surface = (
        "Agent-visible Tool surface 是 `docfit_evidence`、`docfit_check`、`docfit_apply`"
    )
    assert old_tool_surface not in status
    assert "返回结构化 `scoped_closure_v1`" not in status


def test_superseded_semantic_quality_gate_plan_is_only_a_tombstone() -> None:
    plan = (ROOT / "docs/plans/template-semantic-quality-gate-repair-plan.md").read_text(
        encoding="utf-8"
    )

    assert "status: SUPERSEDED" in plan
    assert "retention: historical tombstone only" in plan
    assert "scope.reading_block_id" in plan
    assert "ordered `parts[]`" in plan
    for stale_fragment in [
        "registry_field=",
        "structure_ref=",
        "covered_reading_block_ids",
        "semantic_field",
    ]:
        assert stale_fragment not in plan


def test_superseded_materialization_plan_is_not_active_or_legacy_guidance() -> None:
    plans_readme = (ROOT / "docs/plans/README.md").read_text(encoding="utf-8")
    active_section = plans_readme.split("## 已完成 / 已迁移", maxsplit=1)[0]
    plan = (ROOT / "docs/plans/refactor-post-unit-materialization.md").read_text(
        encoding="utf-8"
    )

    assert "refactor-post-unit-materialization.md" not in active_section
    assert "status: DONE" in plan
    assert "retention: historical tombstone only" in plan
    assert "scope.reading_block_id" in plan
    assert "ordered `parts[]`" in plan
    for stale_fragment in [
        "registry_field=",
        "bound_field_ids",
        "covered_reading_block_ids",
        "slot_id`。",
    ]:
        assert stale_fragment not in plan


def test_superseded_adr_0003_is_only_a_tombstone() -> None:
    adr = (ROOT / "docs/adr/0003-template-semantic-quality-gate-boundaries.md").read_text(
        encoding="utf-8"
    )

    assert "状态: superseded" in adr
    assert "historical tombstone only" in adr
    assert "source_entry_id + ordered parts[]" in adr
    assert "不能成为 judgment scope" in adr
    assert "scope.reading_block_id" not in adr
    for stale_fragment in [
        "registry_field=",
        "structure_ref=",
        "covered_reading_block_ids",
        "bound_field_ids",
    ]:
        assert stale_fragment not in adr


def test_current_module_doc_does_not_expose_post_unit_apply_to_agent() -> None:
    module = (ROOT / "docs/modules/template-extraction.md").read_text(encoding="utf-8")

    assert "提交 `docfit_apply`" not in module
    assert "调用 post-unit 机械检查/物化 Tool" in module


def test_current_module_doc_uses_resolved_units_not_legacy_unit_alias() -> None:
    module = (ROOT / "docs/modules/template-extraction.md").read_text(encoding="utf-8")

    assert "resolved_units" in module
    assert "accepted_units" not in module


def test_testing_entrypoint_separates_generation_smoke_from_eval_gold() -> None:
    testing = (ROOT / "tests/README.md").read_text(encoding="utf-8")
    legacy_pointer = (ROOT / "docs/docfit-02-testing-and-iteration.md").read_text(
        encoding="utf-8"
    )
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    module_router = (ROOT / "docs/modules/README.md").read_text(encoding="utf-8")
    manual_diagnostics = (ROOT / "tests/manual-diagnostics/README.md").read_text(
        encoding="utf-8"
    )

    assert "生成测试只准备输入" in testing
    assert "不要为了跑生成测试去寻找 expected output" in testing
    assert "norecursedirs = [\"manual-diagnostics\"]" in testing
    assert "当前测试入口已移到 [`../tests/README.md`](../tests/README.md)" in legacy_pointer
    assert "docfit-02-testing-and-iteration.md" not in agents
    assert "只有对已生成 Actual 产物离线评分时才读" in module_router
    assert "This directory is not the pytest suite" in manual_diagnostics
