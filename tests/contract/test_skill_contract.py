from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from docfit.tools import FULL_TOOL_NAMES

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _PROJECT_ROOT / ".claude" / "skills"
_SKILL_NAMES = ("docfit-school-extract", "convert-thesis")
_REQUIRED_HEADINGS = (
    "## 触发范围",
    "## 输入与产物",
    "## 不可违反的核心边界",
    "## 根据证据选择下一步",
    "## Tool 与 references 路由",
    "## 完成检查清单",
    "## 最终回复要求",
)
_UNIT_ANALYSIS_FIELDS = {
    "status",
    "confidence",
    "findings",
    "confirmed_rules",
    "uncertainties",
    "dependencies",
    "cross_unit_links",
    "evidence_requests",
    "proposed_operations",
}
_REFERENCE_PATTERN = re.compile(r"\.claude/skills/[A-Za-z0-9_./-]+\.md")


def _skill(name: str) -> tuple[dict[str, Any], str]:
    text = (_SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter_text, body = text.split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_text)
    assert isinstance(frontmatter, dict)
    return frontmatter, body


def _tool_names(body: str) -> set[str]:
    return set(re.findall(r"mcp__docfit__docx_[a-z_]+", body))


def _explicit_references(text: str) -> tuple[Path, ...]:
    references: list[Path] = []
    for match in _REFERENCE_PATTERN.findall(text):
        candidate = _PROJECT_ROOT / match
        assert not candidate.is_symlink()
        path = candidate.resolve()
        assert path.is_relative_to(_SKILLS_ROOT.resolve())
        assert path.is_file()
        if path not in references:
            references.append(path)
    return tuple(references)


def _skill_tree(name: str) -> tuple[str, tuple[Path, ...]]:
    _, body = _skill(name)
    references: list[Path] = []
    queue = list(_explicit_references(body))
    texts = [body]
    while queue:
        reference = queue.pop(0)
        if reference in references:
            continue
        reference_text = reference.read_text(encoding="utf-8")
        references.append(reference)
        texts.append(reference_text)
        queue.extend(_explicit_references(reference_text))
    return "\n".join(texts), tuple(references)


def test_exact_two_domain_skills_are_present() -> None:
    assert {path.parent.name for path in _SKILLS_ROOT.glob("*/SKILL.md")} == set(
        _SKILL_NAMES
    )


def test_skill_frontmatter_is_a_concise_trigger_not_an_implementation_contract() -> None:
    for name in _SKILL_NAMES:
        frontmatter, _ = _skill(name)
        description = frontmatter["description"]
        assert frontmatter["name"] == name
        assert isinstance(description, str)
        assert 25 <= len(description.strip()) <= 90
        assert all(
            token not in description
            for token in ("mcp__", "subagent_type", "docfit-unit-analyst", "不得", "权限")
        )


def test_both_skill_entries_use_the_same_navigable_structure() -> None:
    for name in _SKILL_NAMES:
        _, body = _skill(name)
        positions = [body.index(heading) for heading in _REQUIRED_HEADINGS]
        assert positions == sorted(positions)
        assert "| 当前情况 | 下一步 | 读取参考 |" in body
        assert body.count("- [ ]") >= 6


def test_convert_thesis_uses_only_the_five_public_docfit_tools() -> None:
    body, _ = _skill_tree("convert-thesis")

    assert _tool_names(body) == set(FULL_TOOL_NAMES)
    assert "只选择 intent，绝不选择后端" in body
    assert "传输预算" in body
    assert "局部裁剪图" in body
    assert "可见的应用错误" in body
    assert "损坏的域或交叉引用结果" in body
    assert "阻断性发现" in body
    assert "所有 DOCX 修改只通过 `mcp__docfit__docx_edit` 完成" in body
    assert "第一个候选工作副本必须从目标模板产生" in body
    assert "不得从学生论文副本构建候选后导入模板节" in body
    assert "`import_content_objects`" in body
    assert "Bash/Write 已完全" in body
    assert "没有 DocFit 路径 gate" in body
    assert "在主/子 Agent 分工中，主 Agent 统一承担写入" in body
    assert "不表示 Bash/Write 权限被关闭" in body


def test_school_extract_is_read_only_and_task_scoped() -> None:
    body, _ = _skill_tree("docfit-school-extract")

    assert _tool_names(body) == {
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
    }
    assert "scope: current_task_only" in body
    assert "不修改任何文档" in body
    assert "不是主 Agent 的文件系统 sandbox" in body
    assert "Bash/Write 虽然对主" in body
    assert "Agent 完全开放" in body
    assert "只对当前任务有效" in body
    assert "此 Skill 不修改任何文档" in body


def test_each_skill_tree_contains_only_its_own_domain() -> None:
    extraction, extraction_references = _skill_tree("docfit-school-extract")
    conversion, conversion_references = _skill_tree("convert-thesis")

    assert "学生" not in extraction
    assert "`convert-thesis`" not in extraction
    assert "`docfit-school-extract`" not in conversion
    assert all(
        path.is_relative_to(_SKILLS_ROOT / "docfit-school-extract")
        for path in extraction_references
    )
    assert all(
        path.is_relative_to(_SKILLS_ROOT / "convert-thesis")
        for path in conversion_references
    )
    assert "本 Skill 的终点是带来源定位的学校材料证据" in extraction
    assert "产物包括最终 DOCX" in conversion


def test_each_skill_owns_its_optional_delegation_instructions() -> None:
    for name in _SKILL_NAMES:
        delegation = _SKILLS_ROOT / name / "references" / "delegation-task-packet.md"
        text = delegation.read_text(encoding="utf-8")
        assert "requested_output: unit_analysis_v1" in text
        assert all(field in text for field in _UNIT_ANALYSIS_FIELDS)
        assert "主 Agent" in text
        other_name = next(item for item in _SKILL_NAMES if item != name)
        assert other_name not in text


def test_every_local_reference_is_explicitly_routed_from_skill_md() -> None:
    for name in _SKILL_NAMES:
        _, skill_body = _skill(name)
        skill_root = _SKILLS_ROOT / name
        local_references = tuple(sorted((skill_root / "references").glob("*.md")))
        _, routed_references = _skill_tree(name)
        assert local_references
        for reference in local_references:
            project_relative = reference.relative_to(_PROJECT_ROOT).as_posix()
            assert project_relative in skill_body
            assert reference.resolve() in routed_references


def test_reference_sets_cover_navigation_recovery_and_edge_cases() -> None:
    extraction_refs = {
        path.name
        for path in (_SKILLS_ROOT / "docfit-school-extract" / "references").glob(
            "*.md"
        )
    }
    conversion_refs = {
        path.name
        for path in (_SKILLS_ROOT / "convert-thesis" / "references").glob("*.md")
    }
    common = {
        "delegation-task-packet.md",
        "tool-usage-and-error-recovery.md",
        "scenarios-and-edge-cases.md",
    }
    assert common <= extraction_refs
    assert common <= conversion_refs
    assert {"evidence-and-conflicts.md", "output-schema.md"} <= extraction_refs
    assert {
        "task-evidence-and-conflicts.md",
        "evidence-and-visual-review.md",
        "editing-validation-and-completion.md",
    } <= conversion_refs
