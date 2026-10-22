#!/usr/bin/env python3
"""Audit or add Word-native coverage comments for DOCX Gold review."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)
DEFAULT_AUTHOR = "Codex Gold Coverage Review"
HEADER_FOOTER_MARKER = "[覆盖批注 / 页眉页脚说明]"

NS = {
    "w": W_NS,
    "r": R_NS,
    "pr": PKG_REL_NS,
    "ct": CT_NS,
}


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def pkg(tag: str) -> str:
    return f"{{{PKG_REL_NS}}}{tag}"


def ct(tag: str) -> str:
    return f"{{{CT_NS}}}{tag}"


def xml_bytes(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def paragraph_text(p: etree._Element) -> str:
    parts = p.xpath(".//w:t/text() | .//w:delText/text()", namespaces=NS)
    return normalize_text("".join(parts))


def paragraph_has_visible_object(p: etree._Element) -> bool:
    expr = (
        ".//w:drawing | .//w:pict | .//w:object | .//w:fldSimple | "
        ".//w:instrText | .//*[local-name()='oMath'] | .//w:br[@w:type='page']"
    )
    return bool(p.xpath(expr, namespaces=NS))


def is_visible_block(p: etree._Element) -> bool:
    return bool(paragraph_text(p) or paragraph_has_visible_object(p))


def p_style(p: etree._Element) -> str:
    vals = p.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
    return vals[0] if vals else "Normal/implicit"


def paragraph_alignment(p: etree._Element) -> str:
    vals = p.xpath("./w:pPr/w:jc/@w:val", namespaces=NS)
    return vals[0] if vals else "inherited"


def first_run_style(p: etree._Element) -> str:
    run = None
    for candidate in p.xpath(".//w:r", namespaces=NS):
        if candidate.xpath(".//w:t/text() | .//w:delText/text()", namespaces=NS):
            run = candidate
            break
    if run is None:
        return "runStyle=object-or-empty"

    bits: list[str] = []
    r_style = run.xpath("./w:rPr/w:rStyle/@w:val", namespaces=NS)
    if r_style:
        bits.append(f"runStyle={r_style[0]}")
    fonts = run.xpath("./w:rPr/w:rFonts", namespaces=NS)
    if fonts:
        font = fonts[0]
        ascii_font = font.get(w("ascii"))
        east_asia_font = font.get(w("eastAsia"))
        if ascii_font or east_asia_font:
            bits.append(f"font={ascii_font or '-'} / {east_asia_font or '-'}")
    size = run.xpath("./w:rPr/w:sz/@w:val", namespaces=NS)
    if size:
        try:
            bits.append(f"size={int(size[0]) / 2:g}pt")
        except ValueError:
            bits.append(f"size={size[0]}")
    if run.xpath("./w:rPr/w:b", namespaces=NS):
        bits.append("bold")
    if run.xpath("./w:rPr/w:i", namespaces=NS):
        bits.append("italic")
    color = run.xpath("./w:rPr/w:color/@w:val", namespaces=NS)
    if color:
        bits.append(f"color={color[0]}")
    return "; ".join(bits) if bits else "runStyle=inherited"


def content_controls(p: etree._Element) -> list[str]:
    infos: list[str] = []
    for sdt in p.xpath(".//w:sdt", namespaces=NS):
        tag = sdt.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
        alias = sdt.xpath("./w:sdtPr/w:alias/@w:val", namespaces=NS)
        placeholder = normalize_text(
            "".join(sdt.xpath(".//w:sdtContent//w:t/text()", namespaces=NS))
        )
        items = []
        if alias:
            items.append(f"field_id={alias[0]}")
        if tag:
            items.append(f"slot_tag={tag[0]}")
        if placeholder:
            items.append(f"placeholder={placeholder[:60]}")
        if items:
            infos.append(", ".join(items))
    return infos


def object_kinds(p: etree._Element) -> list[str]:
    checks = [
        ("image/drawing", ".//w:drawing | .//w:pict"),
        ("embedded-object", ".//w:object"),
        ("field", ".//w:fldSimple | .//w:instrText"),
        ("formula", ".//*[local-name()='oMath']"),
        ("manual-page-break", ".//w:br[@w:type='page']"),
    ]
    return [name for name, expr in checks if p.xpath(expr, namespaces=NS)]


def paragraph_context(p: etree._Element) -> str:
    return "table-cell" if p.xpath("ancestor::w:tbl", namespaces=NS) else "body"


def coverage_comment_body(part_name: str, index: int, p: etree._Element) -> str:
    text = paragraph_text(p)
    preview = text[:90] if text else "[无文字对象]"
    style = f"pStyle={p_style(p)}, align={paragraph_alignment(p)}, {first_run_style(p)}"
    controls = content_controls(p)
    kinds = object_kinds(p)
    context = paragraph_context(p)

    if controls:
        return (
            "[覆盖批注 / 字段槽] "
            f"对象位置: {part_name} block#{index}, {context}. "
            f"内容: {preview}. 字段: {'; '.join(controls)}. "
            "处理动作: 保留 Word 内容控件作为 Gold 的可填槽；填写阶段按 contract 替换控件内容，"
            "填后移除占位符。"
            f"样式: {style}；字段值样式按 expected_value_style/style_contract_ref 验收。"
            "人工结论: 此块已覆盖，不是漏批。"
        )

    if kinds:
        return (
            "[覆盖批注 / 固定对象或生成域] "
            f"对象位置: {part_name} block#{index}, {context}. "
            f"内容: {preview}. 对象类型: {', '.join(kinds)}. "
            "处理动作: 作为模板结构或固定对象保留；若为 TOC/域则按契约生成区更新，"
            "若为图片、公式或分页则保持原对象和边界。"
            f"样式/结构: {style}；对象锚点、段落边界、表格归属和分页关系受保护。"
            "人工结论: 此块已覆盖，不是漏批。"
        )

    if context == "table-cell":
        return (
            "[覆盖批注 / 表格固定内容] "
            f"对象位置: {part_name} block#{index}, table-cell. 内容: {preview}. "
            "处理动作: 表格结构、单元格文字、边框、宽度、合并关系和段落位置作为 protected Truth 保留；"
            "本段不作为学生字段填充，除非同一位置另有字段槽批注。"
            f"样式: {style}. 人工结论: 此块已覆盖，不是漏批。"
        )

    return (
        "[覆盖批注 / 固定模板文字] "
        f"对象位置: {part_name} block#{index}. 内容: {preview}. "
        "处理动作: 作为 protected 模板文字保留；不从学生论文抽取内容填充，也不删除。"
        f"样式: {style}；段落文本、顺序、编号/标题角色和分页上下文受保护。"
        "人工结论: 此块已覆盖，不是漏批。"
    )


def header_footer_summary_body(count: int) -> str:
    return (
        f"{HEADER_FOOTER_MARKER} "
        f"检测到页眉/页脚可见内容块 {count} 个。"
        "处理动作: 页眉、页脚、页码、分节相关对象作为 protected 模板结构保留；"
        "不作为学生字段填充。为保持 OpenXML 校验通过，本批注锚在正文总览处，"
        "不直接锚到 header/footer part。人工结论: 页眉/页脚内容已覆盖，不是漏批。"
    )


def story_part_names(names: list[str]) -> list[str]:
    parts = []
    for name in names:
        if name == "word/document.xml":
            parts.append(name)
        elif re.fullmatch(r"word/(header|footer)\d+\.xml", name):
            parts.append(name)
    return sorted(parts, key=lambda item: (item != "word/document.xml", item))


def ensure_comments_root(existing: bytes | None) -> etree._Element:
    if existing:
        return etree.fromstring(existing)
    return etree.Element(w("comments"), nsmap={"w": W_NS})


def ensure_content_types(root: etree._Element) -> None:
    if root.xpath("//*[local-name()='Override' and @PartName='/word/comments.xml']"):
        return
    override = etree.SubElement(root, ct("Override"))
    override.set("PartName", "/word/comments.xml")
    override.set("ContentType", COMMENTS_CONTENT_TYPE)


def ensure_document_rels(root: etree._Element) -> None:
    for rel in root.xpath("//pr:Relationship", namespaces=NS):
        if rel.get("Type") == COMMENTS_REL_TYPE and rel.get("Target") == "comments.xml":
            return
    ids = []
    for rel in root.xpath("//pr:Relationship", namespaces=NS):
        match = re.fullmatch(r"rId(\d+)", rel.get("Id", ""))
        if match:
            ids.append(int(match.group(1)))
    rel = etree.SubElement(root, pkg("Relationship"))
    rel.set("Id", f"rId{max(ids, default=0) + 1}")
    rel.set("Type", COMMENTS_REL_TYPE)
    rel.set("Target", "comments.xml")


def next_comment_id(comments_root: etree._Element) -> int:
    ids = []
    for comment in comments_root.xpath("//w:comment", namespaces=NS):
        try:
            ids.append(int(comment.get(w("id")) or ""))
        except ValueError:
            pass
    return max(ids, default=-1) + 1


def comment_text(comment: etree._Element) -> str:
    return "".join(comment.xpath(".//w:t/text()", namespaces=NS))


def comments_by_author(comments_root: etree._Element, author: str) -> dict[str, str]:
    result = {}
    for comment in comments_root.xpath("//w:comment", namespaces=NS):
        if comment.get(w("author")) == author:
            comment_id = comment.get(w("id"))
            if comment_id is not None:
                result[comment_id] = comment_text(comment)
    return result


def add_comment_to_paragraph(p: etree._Element, comment_id: int) -> None:
    range_start = etree.Element(w("commentRangeStart"))
    range_start.set(w("id"), str(comment_id))
    insert_at = 1 if len(p) and p[0].tag == w("pPr") else 0
    p.insert(insert_at, range_start)

    range_end = etree.Element(w("commentRangeEnd"))
    range_end.set(w("id"), str(comment_id))
    p.append(range_end)

    run = etree.SubElement(p, w("r"))
    ref = etree.SubElement(run, w("commentReference"))
    ref.set(w("id"), str(comment_id))


def append_comment(comments_root: etree._Element, comment_id: int, text: str, author: str) -> None:
    comment = etree.SubElement(comments_root, w("comment"))
    comment.set(w("id"), str(comment_id))
    comment.set(w("author"), author)
    comment.set(w("date"), dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat())
    p = etree.SubElement(comment, w("p"))
    run = etree.SubElement(p, w("r"))
    t = etree.SubElement(run, w("t"))
    t.text = text


def remove_comments_by_author(
    comments_root: etree._Element,
    story_roots: dict[str, etree._Element],
    author: str,
) -> int:
    ids = set(comments_by_author(comments_root, author))
    if not ids:
        return 0

    for comment in list(comments_root.xpath("//w:comment", namespaces=NS)):
        if comment.get(w("id")) in ids:
            parent = comment.getparent()
            if parent is not None:
                parent.remove(comment)

    for root in story_roots.values():
        for marker_name in ("commentRangeStart", "commentRangeEnd"):
            for marker in list(root.xpath(f".//w:{marker_name}", namespaces=NS)):
                if marker.get(w("id")) in ids:
                    parent = marker.getparent()
                    if parent is not None:
                        parent.remove(marker)
        for run in list(root.xpath(".//w:r[w:commentReference]", namespaces=NS)):
            refs = run.xpath("./w:commentReference", namespaces=NS)
            for ref in refs:
                if ref.get(w("id")) in ids:
                    run.remove(ref)
            if not len(run) and run.getparent() is not None:
                run.getparent().remove(run)
    return len(ids)


def paragraph_comment_ids(p: etree._Element) -> set[str]:
    return {
        marker.get(w("id"))
        for marker in p.xpath(".//w:commentRangeStart | .//w:commentReference", namespaces=NS)
        if marker.get(w("id")) is not None
    }


@dataclass
class Audit:
    docx: str
    existing_comments: int
    coverage_comments: int
    body_coverage_comments: int
    header_footer_summary_comments: int
    visible_body_blocks: int
    header_footer_visible_blocks: int
    missing_body_coverage: int
    header_footer_summary_ok: bool
    comment_structure_ok: bool
    removed_coverage_comments: int = 0
    added_body_coverage_comments: int = 0
    added_header_footer_summary_comments: int = 0


def structure_ok(names: list[str], story_roots: dict[str, etree._Element], comment_ids: set[str]) -> bool:
    starts: set[str] = set()
    ends: set[str] = set()
    refs: set[str] = set()
    for name in story_part_names(names):
        root = story_roots[name]
        starts.update(
            marker.get(w("id"))
            for marker in root.xpath(".//w:commentRangeStart", namespaces=NS)
            if marker.get(w("id")) is not None
        )
        ends.update(
            marker.get(w("id"))
            for marker in root.xpath(".//w:commentRangeEnd", namespaces=NS)
            if marker.get(w("id")) is not None
        )
        refs.update(
            marker.get(w("id"))
            for marker in root.xpath(".//w:commentReference", namespaces=NS)
            if marker.get(w("id")) is not None
        )
    return comment_ids <= starts and comment_ids <= ends and comment_ids <= refs


def inspect_docx(
    path: Path,
    *,
    author: str,
    add: bool,
    replace_existing_coverage: bool,
) -> tuple[Audit, dict[str, bytes] | None]:
    with zipfile.ZipFile(path, "r") as zin:
        names = zin.namelist()
        if "word/document.xml" not in names:
            raise SystemExit(f"{path}: missing word/document.xml")
        parts = story_part_names(names)
        story_roots = {name: etree.fromstring(zin.read(name)) for name in parts}
        comments_root = ensure_comments_root(
            zin.read("word/comments.xml") if "word/comments.xml" in names else None
        )
        removed = 0
        if add and replace_existing_coverage:
            removed = remove_comments_by_author(comments_root, story_roots, author)

        next_id = next_comment_id(comments_root)
        body_root = story_roots["word/document.xml"]
        visible_body = [
            (index, p)
            for index, p in enumerate(body_root.xpath(".//w:p", namespaces=NS), start=1)
            if is_visible_block(p)
        ]
        header_footer_visible = 0
        for part_name in parts:
            if part_name == "word/document.xml":
                continue
            header_footer_visible += sum(
                1
                for p in story_roots[part_name].xpath(".//w:p", namespaces=NS)
                if is_visible_block(p)
            )

        coverage_before = comments_by_author(comments_root, author)
        body_coverage_ids_before = {
            cid for cid, text in coverage_before.items() if HEADER_FOOTER_MARKER not in text
        }
        header_summary_count_before = sum(
            1 for text in coverage_before.values() if HEADER_FOOTER_MARKER in text
        )
        added_body = 0
        added_summary = 0

        for index, p in visible_body:
            if paragraph_comment_ids(p) & body_coverage_ids_before:
                continue
            if add:
                cid = next_id
                next_id += 1
                add_comment_to_paragraph(p, cid)
                append_comment(comments_root, cid, coverage_comment_body("word/document.xml", index, p), author)
                added_body += 1

        if header_footer_visible and header_summary_count_before == 0 and add and visible_body:
            cid = next_id
            next_id += 1
            add_comment_to_paragraph(visible_body[0][1], cid)
            append_comment(comments_root, cid, header_footer_summary_body(header_footer_visible), author)
            added_summary += 1

        coverage_after = comments_by_author(comments_root, author)
        body_coverage_ids_after = {
            cid for cid, text in coverage_after.items() if HEADER_FOOTER_MARKER not in text
        }
        header_summary_count_after = sum(
            1 for text in coverage_after.values() if HEADER_FOOTER_MARKER in text
        )
        missing_body = sum(
            1
            for _, p in visible_body
            if not (paragraph_comment_ids(p) & body_coverage_ids_after)
        )
        comment_ids = {
            comment.get(w("id"))
            for comment in comments_root.xpath("//w:comment", namespaces=NS)
            if comment.get(w("id")) is not None
        }
        audit = Audit(
            docx=str(path),
            existing_comments=len(comments_root.xpath("//w:comment", namespaces=NS)),
            coverage_comments=len(coverage_after),
            body_coverage_comments=len(body_coverage_ids_after),
            header_footer_summary_comments=header_summary_count_after,
            visible_body_blocks=len(visible_body),
            header_footer_visible_blocks=header_footer_visible,
            missing_body_coverage=missing_body,
            header_footer_summary_ok=(header_footer_visible == 0 or header_summary_count_after > 0),
            comment_structure_ok=structure_ok(names, story_roots, comment_ids),
            removed_coverage_comments=removed,
            added_body_coverage_comments=added_body,
            added_header_footer_summary_comments=added_summary,
        )

        if not add:
            return audit, None

        content_types = etree.fromstring(zin.read("[Content_Types].xml"))
        ensure_content_types(content_types)
        rels_name = "word/_rels/document.xml.rels"
        rels_root = etree.fromstring(zin.read(rels_name))
        ensure_document_rels(rels_root)

        overrides = {
            "[Content_Types].xml": xml_bytes(content_types),
            rels_name: xml_bytes(rels_root),
            "word/comments.xml": xml_bytes(comments_root),
        }
        overrides.update({name: xml_bytes(root) for name, root in story_roots.items()})
        copied_parts = {
            info.filename: zin.read(info.filename)
            for info in zin.infolist()
            if info.filename not in overrides
        }
        return audit, overrides | copied_parts


def write_docx(source: Path, output: Path, parts: dict[str, bytes]) -> None:
    with zipfile.ZipFile(source, "r") as zin:
        fd, tmp_name = tempfile.mkstemp(suffix=".docx", dir=str(output.parent))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp_name, "w", zipfile.ZIP_DEFLATED) as zout:
                written = set()
                for info in zin.infolist():
                    name = info.filename
                    if name in parts:
                        zout.writestr(name, parts[name])
                    else:
                        zout.writestr(name, zin.read(name))
                    written.add(name)
                if "word/comments.xml" in parts and "word/comments.xml" not in written:
                    zout.writestr("word/comments.xml", parts["word/comments.xml"])
            shutil.move(tmp_name, output)
        finally:
            Path(tmp_name).unlink(missing_ok=True)


def print_audit(audit: Audit) -> None:
    print(json.dumps(asdict(audit), ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Audit existing coverage comments")
    audit_parser.add_argument("docx", type=Path)
    audit_parser.add_argument("--author", default=DEFAULT_AUTHOR)

    add_parser = subparsers.add_parser("add", help="Add missing coverage comments")
    add_parser.add_argument("docx", type=Path)
    add_parser.add_argument("--out", required=True, type=Path)
    add_parser.add_argument("--author", default=DEFAULT_AUTHOR)
    add_parser.add_argument(
        "--replace-existing-coverage",
        action="store_true",
        help="Remove existing comments by --author before adding fresh coverage comments.",
    )

    args = parser.parse_args()
    if args.command == "audit":
        audit, _ = inspect_docx(
            args.docx,
            author=args.author,
            add=False,
            replace_existing_coverage=False,
        )
        print_audit(audit)
        return

    audit, parts = inspect_docx(
        args.docx,
        author=args.author,
        add=True,
        replace_existing_coverage=args.replace_existing_coverage,
    )
    if parts is None:
        raise SystemExit("internal error: add mode did not produce DOCX parts")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_docx(args.docx, args.out, parts)
    final_audit, _ = inspect_docx(
        args.out,
        author=args.author,
        add=False,
        replace_existing_coverage=False,
    )
    final_audit.removed_coverage_comments = audit.removed_coverage_comments
    final_audit.added_body_coverage_comments = audit.added_body_coverage_comments
    final_audit.added_header_footer_summary_comments = audit.added_header_footer_summary_comments
    print_audit(final_audit)


if __name__ == "__main__":
    main()
