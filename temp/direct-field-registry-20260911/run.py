"""Direct API experiment with the actual complete vocabulary and explicit examples."""

import asyncio
import importlib.util
import json
from pathlib import Path

from docfit.fields import FieldRegistrySnapshot


BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
spec = importlib.util.spec_from_file_location(
    "direct_transport", BASE.parent / "direct-field-api-20260911/probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.BASE = BASE

registry = FieldRegistrySnapshot.load(
    REPO / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
)
vocabulary = registry.pre_input_vocabulary()
fields = [
    {
        **{key: entry[key] for key in (
            "field_id", "label", "meaning", "content_type", "cardinality",
            "parent_field_id", "value_sources",
        ) if key in entry},
        "allowed_part_roles": entry["usage_affordance"]["allowed_part_roles"],
    }
    for entry in vocabulary["fields"]
]

GUIDANCE = """把学校论文封面原文拆成可填写模板的语义片段，并从给定语义表选择字段。

拆分粒度：一个 part 承担一个字段的完整值，或一种非填写责任。标签、填写值、格式说明分别表达。相邻值属于不同字段就拆开；语义表已有复合字段且原文表达该复合值时，保留一个 part，不把学号拆成若干位，也不另造子字段。

角色：fixed_label 是成品仍原样保留的正式文字、标签或排版间距；fill_slot 是被相应真实字段值整体替换的原文；style_only 是应落实到相关内容、但不作为成品文字显示的格式/填写说明。需说明样式约束谁时，可写简短 note。原文有其他责任时可使用 manual_region、cleanup、body_structure、generated_content，按其含义和语义表允许角色判断。

语义表给出可选择的字段，不是本页应有字段清单。只有原文确实承担该字段值的位置才绑定 field_id；不能为凑表添加槽。optional 不表示可以忽略原文已经存在的填写责任。未找到适用字段则保留已确认的责任，以 open_questions 说明缺口。

输出是原文分段标注，不是生成填写后的文字。parts[].text 逐字复制原文，依次拼回该条原文，不改写、不重复、不追加内容。普通空白可跟随相邻非填写片段，不必逐字符拆分。把 fill_slot 想象成一个真实值，检查固定标签是否仍在、不同值是否各归其位。

只输出 JSON 对象 {"items":[{"n":输入编号,"parts":[{"text":"原文片段","role":"角色","field_id":"仅需要字段的片段提供"}]}]}。不要输出示例的条目，也不要输出解释段落。
"""

EXAMPLES = [
    {
        "说明": "文档类别标题是固定文字；紧接的题名提示独占实际题名位置，另无填写区。后者整段替换，不能保留提示前缀或追加新槽。",
        "输入": [
            {"n": 101, "text": "本科毕业论文封面（居中）"},
            {"n": 102, "text": "本科毕业论文中文标题（黑体）"},
        ],
        "输出": {"items": [
            {"n": 101, "parts": [
                {"text": "本科毕业论文封面", "role": "fixed_label"},
                {"text": "（居中）", "role": "style_only", "note": "约束固定文档标题"},
            ]},
            {"n": 102, "parts": [
                {"text": "本科毕业论文中文标题", "role": "fill_slot", "field_id": "thesis.title.zh"},
                {"text": "（黑体）", "role": "style_only", "note": "约束中文题名"},
            ]},
        ]},
    },
    {
        "说明": "前导间距和标签保留，学号是一个完整字段值。",
        "输入": [{"n": 103, "text": "□□学籍编号：S20260001"}],
        "输出": {"items": [{"n": 103, "parts": [
            {"text": "□□学籍编号：", "role": "fixed_label"},
            {"text": "S20260001", "role": "fill_slot", "field_id": "author.student_id"},
        ]}]},
    },
    {
        "说明": "同一行分别有作者姓名、导师姓名、导师职称三个字段。导师姓名和职称紧挨着也需分开；括号说明约束标签。",
        "输入": [{"n": 104, "text": "作者：王宁；指导教师（宋体）：陈华副教授"}],
        "输出": {"items": [{"n": 104, "parts": [
            {"text": "作者：", "role": "fixed_label"},
            {"text": "王宁", "role": "fill_slot", "field_id": "author.name.zh"},
            {"text": "；指导教师", "role": "fixed_label"},
            {"text": "（宋体）", "role": "style_only", "note": "约束指导教师标签"},
            {"text": "：", "role": "fixed_label"},
            {"text": "陈华", "role": "fill_slot", "field_id": "advisor.name.zh"},
            {"text": "副教授", "role": "fill_slot", "field_id": "advisor.title"},
        ]}]},
    },
    {
        "说明": "学校在一个位置整体填写年级、专业和班级，语义表提供 author.cohort_class 复合字段；值整体替换，标签保留。",
        "输入": [{"n": 105, "text": "年级、专业、班级：2025级园林（3）班"}],
        "输出": {"items": [{"n": 105, "parts": [
            {"text": "年级、专业、班级：", "role": "fixed_label"},
            {"text": "2025级园林（3）班", "role": "fill_slot", "field_id": "author.cohort_class"},
        ]}]},
    },
]


def prepare() -> str:
    by_id = {field["field_id"]: field for field in fields}
    for example in EXAMPLES:
        expected = {row["n"]: row["text"] for row in example["输入"]}
        for row in example["输出"]["items"]:
            assert "".join(part["text"] for part in row["parts"]) == expected[row["n"]]
            for part in row["parts"]:
                if "field_id" in part:
                    assert part["role"] in by_id[part["field_id"]]["allowed_part_roles"]
    assert [field["field_id"] for field in fields] == vocabulary["allowed_field_ids"]
    probe.save(BASE / "vocabulary-provenance.json", vocabulary)
    probe.save(BASE / "semantic-table.json", fields)
    probe.save(BASE / "examples.json", EXAMPLES)
    system = (GUIDANCE + "\n完整字段语义表（保持 Registry 原顺序）：\n"
              + json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
              + "\n完整拆分示例：\n"
              + json.dumps(EXAMPLES, ensure_ascii=False, separators=(",", ":")))
    (BASE / "system-prompt.txt").write_text(system + "\n")
    probe.save(BASE / "manifest.json", {
        "registry": registry.identity(), "field_count": len(fields),
        "vocabulary_digest": vocabulary["digest"], "example_count": len(EXAMPLES),
        "actual_orders": [3, 4, 6, 7, 9, 10, 11, 12],
        "system_prompt_characters": len(system), "model": probe.backend.model,
        "thinking": "disabled", "temperature": 1, "max_tokens": 4000,
        "verification_level": "real direct API semantic experiment; not product E2E",
    })
    return system


async def main() -> None:
    system = prepare()
    await asyncio.gather(*(
        probe.run(f"registry-examples-{i}", [3, 4, 6, 7, 9, 10, 11, 12], system_prompt=system)
        for i in range(1, 4)
    ))


if __name__ == "__main__":
    asyncio.run(main())
