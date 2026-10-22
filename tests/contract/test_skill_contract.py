from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from docfit.tools import DOCFIT_GENERAL_TOOL_NAMES, DOCFIT_TOOL_SURFACE, FULL_TOOL_NAMES

_CONVERT_THESIS_DOCX_TOOLS = {
    "mcp__docfit__docx_inspect",
    "mcp__docfit__docx_edit",
    "mcp__docfit__docx_render",
    "mcp__docfit__docx_visual_review",
    "mcp__docfit__docx_validate",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _PROJECT_ROOT / ".claude" / "skills"
_FIXTURES_ROOT = _PROJECT_ROOT / "tests" / "fixtures"
_DOMAIN_SKILL_NAMES = ("docfit-school-extract", "convert-thesis", "docfit-gold-word-review")
_SKILL_NAMES = ("docfit-school-extract", "convert-thesis")
_CONVERT_REQUIRED_HEADINGS = (
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
_LOCAL_REFERENCE_PATTERN = re.compile(r"\(references/([A-Za-z0-9_.-]+\.md)\)")
_ASSET_PATTERN = re.compile(r"`([A-Za-z0-9_.-]+\.template\.yaml)`")
_SCHOOL_REFERENCE_REQUIRED_HEADINGS = (
    "## 用途",
    "## 触发条件",
    "## 核心判断规则",
    "## 反例",
    "## 不负责事项",
)
_SCHOOL_REFERENCE_FORBIDDEN_TOKENS = (
    "docx_",
    "template_harness",
    "submit_semantic_judgments",
    "subagent_type",
    "input_schema",
    "schema_version",
    "状态机",
)
_SCHOOL_EXTRACT_FORBIDDEN_CANONICAL_FIELD_IDS = (
    "advisor.name.en",
    "submission.date",
    "generated.toc",
    "body.chapters",
    "body.heading.outline1",
    "body.heading.outline2",
    "body.heading.outline3",
    "body.paragraph",
    "references.entries",
    "acknowledgement.body",
    "appendix.title",
    "appendix.body",
)


def _skill(name: str) -> tuple[dict[str, Any], str]:
    text = (_SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter_text, body = text.split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_text)
    assert isinstance(frontmatter, dict)
    return frontmatter, body


def _tool_names(body: str) -> set[str]:
    return set(re.findall(r"mcp__docfit__docx_[a-z_]+", body))


def _canonical_tool_names(body: str) -> set[str]:
    return set(re.findall(r"`(docfit_(?:evidence|check|apply))`", body))


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
    queue = list(_explicit_references(body)) + [
        (_SKILLS_ROOT / name / "references" / match).resolve()
        for match in _LOCAL_REFERENCE_PATTERN.findall(body)
    ]
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


def _school_reference(name: str) -> str:
    _, entry = _skill("docfit-school-extract")
    assert f"(references/{name})" in entry
    return (_SKILLS_ROOT / "docfit-school-extract/references" / name).read_text(encoding="utf-8")


def _span_example_rows(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    examples = []
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = line.strip("|").split("|")
        if len(cells) != 3 or "→" not in cells[1]:
            continue
        source = re.findall(r"`([^`]*)`", cells[0])[-1]
        parts = re.findall(r"`([^`]*)` → `?(\w+)`?", cells[1])
        assert parts, line
        examples.append((source, parts))
    return examples


def test_expected_domain_skills_are_present() -> None:
    assert {path.parent.name for path in _SKILLS_ROOT.glob("*/SKILL.md")} == set(
        _DOMAIN_SKILL_NAMES
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


def test_conversion_skill_entry_has_a_navigable_structure() -> None:
    _, conversion = _skill("convert-thesis")
    positions = [conversion.index(heading) for heading in _CONVERT_REQUIRED_HEADINGS]
    assert positions == sorted(positions)
    assert "| 当前情况 | 下一步 | 读取参考 |" in conversion
    assert conversion.count("- [ ]") >= 6


def test_school_extract_entry_stays_concise() -> None:
    _, body = _skill("docfit-school-extract")

    assert len(body.splitlines()) <= 115


def test_convert_thesis_uses_only_its_legacy_docfit_tools() -> None:
    body, _ = _skill_tree("convert-thesis")

    assert _tool_names(body) == _CONVERT_THESIS_DOCX_TOOLS
    assert _tool_names(body) <= set(FULL_TOOL_NAMES)
    assert "固定 LibreOffice V2" in body
    assert "`render:v2:`" in body
    assert "intent、provider、backend" in body
    assert "有 cursor" in body
    assert "mapping 不唯一" in body
    assert "裁剪图不能替代完整页面判断" in body
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


def test_school_extract_entry_keeps_execution_protocol_out_of_domain_guidance() -> None:
    _, body = _skill("docfit-school-extract")

    # The schema, prompt and feedback contract own these details. Keeping this
    # denylist on the entry avoids freezing its prose or a second output schema.
    for token in (
        "source_entry",
        "reading_block",
        "range_id",
        "unit_evidence_packet",
        "usage_affordance.allowed_part_roles",
        "scope.",
        "source_hash",
        "candidate_hash",
        "render_ref",
        "object_ref",
        "object_id",
        "target_ref",
        "locator",
        "span_ref",
        "slot_ref",
        "coverage",
        "publish",
        "checkpoint_backend",
        "task_root",
        "stale_ref",
        "fingerprint",
        "reviewed_pages",
        "candidate_render_ref",
        "covered_reading_spans",
        "bound_field_ids",
        "required_field_ids",
        "toc_contract",
        "template_harness",
        "submit_semantic_judgments",
        "docx_",
        "docfit_check",
        "docfit_apply",
        "action_requirement",
        "convert_to_field_slot",
        "deletion_safety",
        "depends_on",
    ):
        assert token not in body, token
    assert _canonical_tool_names(body) <= {"docfit_evidence"}
    assert "不读取学生论文" in body
    assert tuple(entry["name"] for entry in DOCFIT_TOOL_SURFACE) == DOCFIT_GENERAL_TOOL_NAMES


def test_school_extract_unit_boundary_mode_is_boundary_only() -> None:
    _, skill_body = _skill("docfit-school-extract")
    unit_boundary_reference = (
        _SKILLS_ROOT / "docfit-school-extract/references/unit-boundary.md"
    ).read_text(encoding="utf-8")
    module_doc = (_PROJECT_ROOT / "docs/modules/template-extraction.md").read_text(encoding="utf-8")

    assert "始终引用输入中已有的源对象身份" in (unit_boundary_reference)
    assert "字段、生成、样式、删除和清理责任只作为后续 post-unit 判断" in (unit_boundary_reference)
    assert "边界证据不足时返回顶层 `needs_input`" in unit_boundary_reference
    assert "目录缓存中的条目不是正文、摘要、参考文献等真实功能区的边界" in unit_boundary_reference
    assert "目录缓存条目不能作为其他功能区的边界" in skill_body
    assert "页眉页脚标签不能单独创建功能区或充当正文边界" in skill_body
    assert (
        "页眉、页脚、脚注和尾注由 Harness 按原 Word story 建立独立的辅助取证范围"
        in unit_boundary_reference
    )
    assert "不能仅凭页眉页脚出现的名称新增同名 unit" in unit_boundary_reference
    assert (
        "每个单元至少说明固定内容、填写责任、生成机制、样式样本、清理对象"
        not in unit_boundary_reference
    )
    assert "每个边界引用已有 `source_entry_id`" in module_doc
    assert "姓名槽、字段绑定、样式、清理、生成机制和后续 open questions" in module_doc
    assert "以下 proof 字段由 Harness/App 写入，不是 Agent 输出要求" in module_doc
    assert "不确定点或 open questions。" not in module_doc


def test_school_extract_body_example_respects_source_entry_contract() -> None:
    reference = _school_reference("body-structure.md")
    source_rows = re.findall(r"^\| `(source-entry-[^`]+)` \| `([^`]+)` \|", reference, re.M)
    assert source_rows
    assert len(dict(source_rows)) == len(source_rows)
    examples = re.findall(r"```yaml\n(.*?)\n```", reference, re.S)
    assert len(examples) == 1
    judgments = yaml.safe_load(examples[0])
    assert isinstance(judgments, list)
    assert [item["source_entry_id"] for item in judgments] == [key for key, _ in source_rows]
    for judgment, (_, source_text) in zip(judgments, source_rows, strict=True):
        parts = judgment["parts"]
        assert "".join(part["text"] for part in parts) == source_text
        members = [part for part in parts if part.get("field_id")]
        assert len(members) == 1
        assert members[0]["role"] == "body_structure"
    # Repeated paragraph roles must remain separate input members.
    assert len({part["field_id"] for item in judgments for part in item["parts"]}) < len(judgments)


def test_school_extract_toc_units_require_generated_reference_down_drill() -> None:
    generated_reference = (
        _SKILLS_ROOT / "docfit-school-extract/references/generated-content-and-toc.md"
    ).read_text(encoding="utf-8")

    assert "unit 已被识别为目录、图目录、表目录或其它生成清单" in (generated_reference)
    assert "目录 unit 下钻时不能只套用通用生成区抽象" in generated_reference
    assert "学校固定外壳、真实生成机制、结果样式、可见缓存" in generated_reference
    assert "缓存 range 必须由 `generated_content` part 接管" in generated_reference
    assert "### 目录输出结构" in generated_reference
    assert "`toc_contract`" not in generated_reference
    assert "目录 generated judgment 仍是普通 `source_entry_id + parts` 输出" in generated_reference
    assert '"role": "generated_content"' in generated_reference
    assert '"field_id": "输入词表中的目录字段"' in generated_reference
    assert "固定“目录”标题、空行说明、分支标签和格式说明仍按普通 judgment 单独覆盖" in (
        generated_reference
    )
    assert "如果一个目录相关 unit 只包含固定标题、空行或格式说明" in (generated_reference)
    assert "不要只删除缓存，也不要把生成机制只挂到将删除的格式说明上" in (generated_reference)
    assert "旧的目录专属对象形状" in generated_reference
    assert "没有来源标题族和层级证据时返回 `needs_input`" in generated_reference


def test_school_extract_post_unit_semantic_output_vocabulary() -> None:
    text_reference = (
        _SKILLS_ROOT / "docfit-school-extract/references/template-text-classification.md"
    ).read_text(encoding="utf-8")
    registry_reference = (
        _SKILLS_ROOT / "docfit-school-extract/references/registry-interface-binding.md"
    ).read_text(encoding="utf-8")

    assert "### 输出 role 词表" in text_reference
    assert "| role | 含义 | 后续依赖 |" in text_reference
    for role in (
        "fixed_label",
        "fill_slot",
        "cleanup",
        "style_only",
        "manual_region",
        "body_structure",
        "generated_content",
    ):
        assert role in text_reference
    assert "clean_template_treatment" not in text_reference
    assert "`field_id` 只属于需要 Registry 字段的 ordered part" in text_reference
    assert "usage_affordance.allowed_part_roles" in text_reference
    assert "声明正文、作者签名和年月日骨架同属人工签署责任" in text_reference
    assert "`manual_region` 整体判断" in text_reference
    # Reference wording and examples may evolve. Keep the public vocabulary and
    # obsolete-protocol checks here; real Agent runs establish semantic quality.
    for token in ("field_id_vocabulary", "usage_affordance.allowed_part_roles"):
        assert token in registry_reference
    for reference in (text_reference, registry_reference):
        for token in ("source_entry_id", "bound_field_ids", "required_field_ids"):
            assert token not in reference


def test_school_extract_span_examples_preserve_source_text() -> None:
    # Validate the examples the Agent actually reads, not a separate answer fixture.
    # This is document/contract validation, not a model accuracy test.
    for name in ("template-text-classification.md", "object-boundary-and-layout-safety.md"):
        rows = _span_example_rows(_school_reference(name))
        assert rows, name
        for source, parts in rows:
            assert "".join(text for text, _ in parts) == source, (name, source)
            assert all(
                role in {"fixed_label", "fill_slot", "style_only", "manual_region"}
                for _, role in parts
            )


def test_school_extract_instruction_examples_keep_one_complete_value() -> None:
    rows = dict(_span_example_rows(_school_reference("template-text-classification.md")))
    for source in ("题目：________（小二黑体）", "题目：____（小二黑体）____"):
        parts = rows[source]
        assert parts[0] == ("题目：", "fixed_label")
        assert sum(role == "fill_slot" for _, role in parts) == 1
    assert rows["题目：________（小二黑体）"][-1] == ("（小二黑体）", "style_only")
    assert rows["题目：____（小二黑体）____"][-1] == ("____（小二黑体）____", "fill_slot")


def test_school_extract_adjacent_blank_continuation_keeps_one_interface() -> None:
    layout = _school_reference("object-boundary-and-layout-safety.md")
    registry = _school_reference("registry-interface-binding.md")
    assert "只建立一个足以承载完整值的接口" in layout
    assert "真实镜像" in layout
    assert "预留换行空间而重复绑定或借用其他字段" in registry


def test_school_extract_allows_only_supplied_empty_entries_as_blank_field_positions() -> None:
    _, entry = _skill("docfit-school-extract")
    layout = _school_reference("object-boundary-and-layout-safety.md")
    assert "输入明确提供的空白" in entry
    assert "相邻标签和布局" in entry
    assert "不得虚构未提供的空位" in entry
    assert "空文本" in layout
    assert "没有填写依据的空白仍是无字段布局" in layout


def test_school_extract_examples_distinguish_labels_and_value_prompts() -> None:
    rows = dict(_span_example_rows(_school_reference("template-text-classification.md")))
    assert rows["论文题目：________"] == [("论文题目：", "fixed_label"), ("________", "fill_slot")]
    assert rows["论文题目（小二黑体）"] == [
        ("论文题目", "fill_slot"),
        ("（小二黑体）", "style_only"),
    ]
    independent = rows["指导教师：某某副教授"]
    composite = rows["年级专业班级：20××级××专业×班"]
    assert independent[0] == ("指导教师：", "fixed_label")
    assert sum(role == "fill_slot" for _, role in independent) == 2
    assert composite[0] == ("年级专业班级：", "fixed_label")
    assert sum(role == "fill_slot" for _, role in composite) == 1


def test_school_extract_routes_manual_form_guidance_without_duplicating_it() -> None:
    _, entry = _skill("docfit-school-extract")
    classification = _school_reference("template-text-classification.md")
    registry = _school_reference("registry-interface-binding.md")
    assert "人工表单" in entry
    assert "只约束明确点名的区域" in classification
    assert "相邻标签和独立值位置" in classification
    assert "学生基础信息" in classification
    assert "人工责任已经由对应 parts 承载" in classification
    for requirement in (
        "地点不能绑定研究方向",
        "复合字段覆盖年级、专业和班级",
        "整个复合值骨架",
        "不能吞掉同一行",
        "学院、院系或培养单位",
    ):
        assert requirement in registry
    assert "仅修正原文字符或空白传输" in entry
    assert "保持原判断中的字段责任不变" in entry


def test_school_extract_form_narratives_do_not_borrow_unrelated_fields() -> None:
    registry = _school_reference("registry-interface-binding.md")
    for requirement in (
        "变更原因、审批意见或签署内容",
        "不同时间状态或不同预期值",
        "不是真实镜像",
        "表单容器不是正文代表结构",
    ):
        assert requirement in registry


def test_school_extract_submission_date_does_not_cover_signature_dates() -> None:
    registry = _school_reference("registry-interface-binding.md").replace("\n", "")
    assert "论文或文档提交时间字段" in registry
    assert "评阅、签署或审批日期" in registry
    assert "不得绑定该提交时间字段" in registry
    assert "专用字段时保持人工责任" in registry


def test_school_extract_unselected_checkbox_options_remain_manual_choices() -> None:
    classification = _school_reference("template-text-classification.md")
    assert "未预选的复选或单选选项" in classification
    rows = dict(_span_example_rows(_school_reference("object-boundary-and-layout-safety.md")))
    assert rows["□同意 □不同意"] == [("□同意 □不同意", "manual_region")]


def test_school_extract_manual_signature_lines_preserve_boundary_whitespace() -> None:
    rows = dict(_span_example_rows(_school_reference("object-boundary-and-layout-safety.md")))
    assert rows["  签名：______  "] == [
        ("  ", "style_only"),
        ("签名：______", "manual_region"),
        ("  ", "style_only"),
    ]


def test_school_extract_text_fidelity_does_not_assign_character_accounting() -> None:
    _, entry = _skill("docfit-school-extract")
    layout = _school_reference("object-boundary-and-layout-safety.md")
    assert "不同种类的空白" in entry
    assert "不归一化视觉相似字符" in entry
    assert "不换行空格" in layout
    for text in (entry, layout):
        assert "render_sensitive_codepoints" not in text
        assert "按 offset" not in text
    assert "保持原判断中的字段责任不变" in entry


def test_school_extract_spacing_only_blank_remains_fieldless() -> None:
    layout = _school_reference("object-boundary-and-layout-safety.md")
    assert "只承担段间距或留白的空白 entry" in layout
    assert "它不是正文代表成员" in layout
    assert "不绑定 `body_structure` 或其它近似字段" in layout


def test_school_extract_spacing_example_preserves_label_without_literal_boxes() -> None:
    _, entry = _skill("docfit-school-extract")
    example = entry.split("### 分段示例", 1)[1].split("常用角色", 1)[0]
    source = re.search(r"原文是 `([^`]+)`", example)
    assert source is not None
    parts = re.findall(r"^\| `([^`]*)` \| (\w+) \|", example, re.M)
    assert "".join(text for text, _ in parts) == source[1]
    assert parts == [("□□", "style_only"), ("档案编号：", "fixed_label"), ("S20××××", "fill_slot")]
    rows = dict(_span_example_rows(_school_reference("object-boundary-and-layout-safety.md")))
    assert rows["空三行"] == [("空三行", "style_only")]
    assert rows["□□摘要"] == [("□□", "style_only"), ("摘要", "fixed_label")]


def test_body_structure_composite_object_has_one_outer_interface() -> None:
    body_reference = (
        _SKILLS_ROOT / "docfit-school-extract/references/body-structure.md"
    ).read_text(encoding="utf-8")

    assert "一个表格、图片或公式整体只能建立一个相应正文成员接口" in body_reference
    assert "表格单元格" in body_reference
    assert "外层复合对象" in body_reference


def test_school_extract_entry_requires_one_real_collection_interface() -> None:
    _, entry = _skill("docfit-school-extract")
    collection_reference = (
        _SKILLS_ROOT / "docfit-school-extract/references/collections-and-optional-sections.md"
    ).read_text(encoding="utf-8")

    for guidance in (collection_reference,):
        assert "已识别为参考文献或成果集合" in guidance
        assert "同一集合区只选择一个真实代表条目作为集合接口" in guidance
        assert "其余格式样例按清理判断" in guidance
        assert "真实镜像输出区" in guidance
        assert "集合标题不能代替条目接口" in guidance
        assert "集合标题没有专用字段时保持固定内容" in guidance
        assert "不得因样式或大纲级别改绑正文章标题字段" in guidance


def test_school_extract_entry_requires_appendix_body_interface() -> None:
    _, entry = _skill("docfit-school-extract")
    collection_reference = (
        _SKILLS_ROOT / "docfit-school-extract/references/collections-and-optional-sections.md"
    ).read_text(encoding="utf-8")

    for guidance in (collection_reference,):
        assert "附录没有真实内容样例" in guidance
        assert (
            "必须把可见说明段的合适正文位置判断为一个带字段的 `fill_slot` 或 `body_structure` part"
        ) in guidance
        assert "以词表允许角色为准" in guidance
        assert "词表无安全字段则返回 `needs_input`" in guidance
        assert "不得把整段只判为 `cleanup`" in guidance
        assert "不可见空段或宿主另行建立接口" in guidance


def test_school_extract_skill_tree_does_not_seed_canonical_field_ids() -> None:
    extraction, _ = _skill_tree("docfit-school-extract")

    for field_id in _SCHOOL_EXTRACT_FORBIDDEN_CANONICAL_FIELD_IDS:
        assert field_id not in extraction


def test_school_extract_does_not_route_runtime_harness_assets() -> None:
    _, body = _skill("docfit-school-extract")
    skill_root = _SKILLS_ROOT / "docfit-school-extract"
    assets = tuple(sorted((skill_root / "assets").glob("*.template.yaml")))
    assert assets == ()
    routed = set(_ASSET_PATTERN.findall(body))
    assert routed == set()


def test_each_skill_tree_contains_only_its_own_domain() -> None:
    extraction, extraction_references = _skill_tree("docfit-school-extract")
    conversion, conversion_references = _skill_tree("convert-thesis")

    assert "`convert-thesis`" not in extraction
    assert "`docfit-school-extract`" not in conversion
    assert all(
        path.is_relative_to(_SKILLS_ROOT / "docfit-school-extract")
        for path in extraction_references
    )
    assert all(
        path.is_relative_to(_SKILLS_ROOT / "convert-thesis") for path in conversion_references
    )
    assert "干净、可填写、可复用" in extraction
    assert "产物包括最终 DOCX" in conversion


def test_conversion_skill_owns_optional_delegation_instructions() -> None:
    conversion = (_SKILLS_ROOT / "convert-thesis/references/delegation-task-packet.md").read_text(
        encoding="utf-8"
    )
    assert "requested_output: unit_analysis_v1" in conversion
    assert all(field in conversion for field in _UNIT_ANALYSIS_FIELDS)


def test_school_extract_skill_does_not_route_delegation_strategy() -> None:
    _, extraction = _skill("docfit-school-extract")

    assert not (_SKILLS_ROOT / "docfit-school-extract/references/delegation-strategy.md").exists()
    assert "delegation-strategy.md" not in extraction
    assert "Subagent" not in extraction
    assert "不委派" in extraction


def test_every_local_reference_is_explicitly_routed_from_skill_md() -> None:
    for name in _SKILL_NAMES:
        _, skill_body = _skill(name)
        skill_root = _SKILLS_ROOT / name
        local_references = tuple(sorted((skill_root / "references").glob("*.md")))
        _, routed_references = _skill_tree(name)
        assert local_references
        for reference in local_references:
            project_relative = reference.relative_to(_PROJECT_ROOT).as_posix()
            assert f"(references/{reference.name})" in skill_body or project_relative in skill_body
            assert reference.resolve() in routed_references


def test_reference_sets_cover_navigation_recovery_and_edge_cases() -> None:
    extraction_refs = {
        path.name for path in (_SKILLS_ROOT / "docfit-school-extract" / "references").glob("*.md")
    }
    conversion_refs = {
        path.name for path in (_SKILLS_ROOT / "convert-thesis" / "references").glob("*.md")
    }
    assert extraction_refs == {
        "body-structure.md",
        "collections-and-optional-sections.md",
        "completion-and-visual-review.md",
        "judgment-context-and-conflicts.md",
        "generated-content-and-toc.md",
        "object-boundary-and-layout-safety.md",
        "registry-interface-binding.md",
        "style-contract-boundary.md",
        "template-text-classification.md",
        "unit-boundary.md",
    }
    assert {
        "delegation-task-packet.md",
        "tool-usage-and-error-recovery.md",
        "scenarios-and-edge-cases.md",
        "task-evidence-and-conflicts.md",
        "evidence-and-visual-review.md",
        "editing-validation-and-completion.md",
    } <= conversion_refs


def test_school_extract_references_are_p1_acceptable_modules() -> None:
    for reference in (_SKILLS_ROOT / "docfit-school-extract" / "references").glob("*.md"):
        text = reference.read_text(encoding="utf-8")
        positions = [text.index(heading) for heading in _SCHOOL_REFERENCE_REQUIRED_HEADINGS]
        assert positions == sorted(positions), reference
        assert all(token not in text for token in _SCHOOL_REFERENCE_FORBIDDEN_TOKENS), reference


def test_school_extract_static_routing_fixtures_point_to_available_references() -> None:
    _, skill_body = _skill("docfit-school-extract")
    for fixture_name, question_key in (
        ("p1_reference_trace.yaml", None),
        ("p3_skill_trace.yaml", "domain_question"),
    ):
        # These fixtures check navigation only; they do not run an Agent or
        # demonstrate that it makes the expected semantic judgment.
        trace = yaml.safe_load(
            (_FIXTURES_ROOT / "template_extraction" / fixture_name).read_text(encoding="utf-8")
        )
        assert isinstance(trace, dict)
        question = trace[question_key] if question_key else trace
        expected_reference = question["expected_reference"]
        assert f"(references/{expected_reference})" in skill_body
        reference = _SKILLS_ROOT / "docfit-school-extract" / "references" / expected_reference
        reference_text = reference.read_text(encoding="utf-8")
        assert all(term in reference_text for term in trace.get("expected_reference_terms", ()))
