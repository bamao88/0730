from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from docfit.tools import FULL_TOOL_NAMES

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _PROJECT_ROOT / ".claude" / "skills"
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


def _skill(name: str) -> tuple[dict[str, Any], str]:
    text = (_SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter_text, body = text.split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_text)
    assert isinstance(frontmatter, dict)
    return frontmatter, body


def _tool_names(body: str) -> set[str]:
    return set(re.findall(r"mcp__docfit__docx_[a-z_]+", body))


def test_exact_two_domain_skills_are_present() -> None:
    assert {path.parent.name for path in _SKILLS_ROOT.glob("*/SKILL.md")} == {
        "docfit-school-extract",
        "convert-thesis",
    }


def test_skill_frontmatter_names_and_trigger_descriptions_match() -> None:
    for name in ("docfit-school-extract", "convert-thesis"):
        frontmatter, _ = _skill(name)
        assert frontmatter["name"] == name
        assert isinstance(frontmatter["description"], str)
        assert len(frontmatter["description"].split()) >= 20


def test_convert_thesis_uses_only_the_five_public_docfit_tools() -> None:
    _, body = _skill("convert-thesis")

    assert _tool_names(body) == set(FULL_TOOL_NAMES)
    assert "edit OOXML directly" in body
    assert "Choose the intent, never the backend" in body
    assert "within the Tool and SDK transport budget" in body
    assert "request focused crops" in body
    assert "visible application error markers" in body
    assert "broken field or" in body
    assert "cross-reference results" in body
    assert "blocking findings" in body


def test_school_extract_is_read_only_and_task_scoped() -> None:
    _, body = _skill("docfit-school-extract")

    assert _tool_names(body) == {
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
    }
    assert "scope: current_task_only" in body
    assert "Do not modify the template or thesis" in body
    assert "Do not create a school directory" in body


def test_both_skills_define_optional_bounded_delegation() -> None:
    for name in ("docfit-school-extract", "convert-thesis"):
        _, body = _skill(name)
        assert "subagent_type: docfit-unit-analyst" in body
        assert "unit_analysis_v1" in body
        assert all(field in body for field in _UNIT_ANALYSIS_FIELDS)
        assert "fixed threshold" in body or "thresholds" in body
