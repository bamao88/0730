"""Build a task-local DocFit edit plan from the bound inspection snapshot."""

from __future__ import annotations

import json
import sys
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parent
INSPECTION = TASK_ROOT / "evidence" / "source-inspect.json"
PLAN = TASK_ROOT / "work" / "clean-plan.json"


# Object positions are bound to the inspected source snapshot. Every target_ref in the
# emitted plan still carries the source SHA-256 and fingerprint checked by docx_edit.
REPLACEMENTS: dict[int, str] = {
    74: "【论文中文题目】",
    75: "摘  要",
    76: "",
    77: "",
    78: "",
    79: "",
    80: "【中文摘要正文】",
    82: "关键词：【关键词1；关键词2；关键词3】",
    83: "【ENGLISH THESIS TITLE】",
    84: "ABSTRACT",
    85: "",
    86: "",
    87: "【英文摘要正文】",
    90: "KEY WORDS: 【keyword 1; keyword 2; keyword 3】",
    93: "第一章 文献综述",
    94: "",
    95: "",
    96: "",
    97: "【文献综述正文】",
    98: "1 【一级节标题】",
    99: "【本节正文】",
    100: "1.1 【二级节标题】",
    101: "【本小节正文】",
    102: "",
    103: "",
    104: "",
    105: "",
    107: "第X章 【正文标题】",
    108: "",
    109: "",
    110: "",
    111: "",
    112: "【本章正文】",
    113: "1 【一级节标题】",
    114: "【本节正文】",
    115: "1.1 【二级节标题】",
    116: "【本小节正文】",
    117: "",
    118: "",
    119: "",
    120: "",
    121: "",
    122: "",
    123: "",
    124: "",
    125: "",
    126: "",
    130: "",
    131: "",
    132: "",
    133: "",
    134: "【结论与展望正文】",
    137: "",
    138: "",
    139: "",
    140: "",
    141: "",
    142: "【参考文献条目】",
    143: "",
    144: "",
    145: "",
    146: "",
    147: "",
    148: "",
    149: "",
    150: "",
    151: "",
    152: "",
    153: "",
    154: "",
    155: "",
    158: "附  录  【附录名称】",
    159: "【附录内容；如不适用，可删除本节】",
    162: "相关的学术成果目录",
    163: "【相关学术成果；如不适用，可删除本节】",
    166: "致  谢",
    167: "",
    168: "",
    169: "【致谢正文】",
}

EXPECTED_OVERRIDES: dict[int, str] = {
    74: "论文题目",
}


def main() -> None:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    objects = inspection["objects"]
    operations: list[dict[str, object]] = []

    for index, replacement in REPLACEMENTS.items():
        item = objects[index]
        expected = EXPECTED_OVERRIDES.get(index, item["text"])
        if not expected:
            raise ValueError(f"object {index} unexpectedly has no text")
        # The current docx_edit postcondition cannot prove an object that was
        # removed by an empty-string replacement. A non-breaking space keeps
        # the paragraph/field carrier alive while remaining visibly blank.
        safe_replacement = replacement if replacement else "\u00a0"
        operations.append(
            {
                "action": "replace_text",
                "target_ref": item["object_ref"],
                "expected_text": expected,
                "replacement": safe_replacement,
            }
        )

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else len(operations)
    destination = (
        TASK_ROOT / sys.argv[3]
        if len(sys.argv) > 3
        else PLAN
    )
    plan = {"operations": operations[start:end]}
    destination.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
