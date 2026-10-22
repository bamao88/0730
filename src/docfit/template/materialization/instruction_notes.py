"""Instruction-note text classification for template materialization."""

from __future__ import annotations

import re

INLINE_PARENTHETICAL_RE = re.compile(r"\s*[（(](?P<note>[^（）()]*)[）)]")
FORMAT_INSTRUCTION_NOTE_RE = re.compile(
    r"(?:"
    r"[一二三四五六七八九十小初]+号"
    r"|[0-9]+(?:\.[0-9]+)?磅"
    r"|times\s+new\s+roman"
    r"|字体|字号|格式|要求|黑体|宋体|楷体|仿宋|隶书|华文"
    r"|加粗|居中|顶格|书写|序数|大写|空一格|另起一页|参照|用全称|全称"
    r")",
    re.IGNORECASE,
)


def is_instruction_parenthetical(note: str) -> bool:
    normalized = " ".join(note.split())
    return bool(normalized) and FORMAT_INSTRUCTION_NOTE_RE.search(normalized) is not None


def strip_instruction_parentheticals(text: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        note = match.group("note")
        return "" if is_instruction_parenthetical(note) else match.group(0)

    return INLINE_PARENTHETICAL_RE.sub(replacement, text)
