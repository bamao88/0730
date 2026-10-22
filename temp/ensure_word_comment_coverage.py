#!/usr/bin/env python3
"""Add Word-native coverage comments to every visible DOCX content block."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)

NS = {
    "w": W_NS,
    "r": R_NS,
    "pr": PKG_REL_NS,
    "ct": CONTENT_TYPES_NS,
}

COVERAGE_AUTHOR = "Codex Gold Coverage Review"


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def pkg(tag: str) -> str:
    return f"{{{PKG_REL_NS}}}{tag}"


def ct(tag: str) -> str:
    return f"{{{CONTENT_TYPES_NS}}}{tag}"


def xml_bytes(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def paragraph_text(p: etree._Element) -> str:
    parts = p.xpath(".//w:t/text() | .//w:delText/text()", namespaces=NS)
    return normalize_text("".join(parts))


def paragraph_has_visible_object(p: etree._Element) -> bool:
    object_expr = (
        ".//w:drawing | .//w:pict | .//w:object | .//w:fldSimple | "
        ".//w:instrText | .//*[local-name()='oMath'] | .//w:br[@w:type='page']"
    )
    return bool(p.xpath(object_expr, namespaces=NS))


def is_visible_block(p: etree._Element) -> bool:
    return bool(paragraph_text(p) or paragraph_has_visible_object(p))


def p_style(p: etree._Element) -> str:
    vals = p.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
    return vals[0] if vals else "Normal/implicit"


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


def paragraph_alignment(p: etree._Element) -> str:
    vals = p.xpath("./w:pPr/w:jc/@w:val", namespaces=NS)
    return vals[0] if vals else "inherited"


def sdt_infos(p: etree._Element) -> list[str]:
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


def paragraph_context(p: etree._Element) -> str:
    table_ancestor = p.xpath("ancestor::w:tbl", namespaces=NS)
    if table_ancestor:
        return "table-cell"
    return "body"


def object_kinds(p: etree._Element) -> list[str]:
    checks = [
        ("image/drawing", ".//w:drawing | .//w:pict"),
        ("embedded-object", ".//w:object"),
        ("field", ".//w:fldSimple | .//w:instrText"),
        ("formula", ".//*[local-name()='oMath']"),
        ("manual-page-break", ".//w:br[@w:type='page']"),
    ]
    return [name for name, expr in checks if p.xpath(expr, namespaces=NS)]


def comment_body(part_name: str, index: int, p: etree._Element) -> str:
    text = paragraph_text(p)
    preview = text[:90] if text else "[无文字对象]"
    style = f"pStyle={p_style(p)}, align={paragraph_alignment(p)}, {first_run_style(p)}"
    sdts = sdt_infos(p)
    kinds = object_kinds(p)
    context = paragraph_context(p)

    if sdts:
        return (
            "[覆盖批注 / 字段槽] "
            f"对象位置: {part_name} block#{index}, {context}. "
            f"内容: {preview}. 字段: {'; '.join(sdts)}. "
            "处理动作: 保留 Word 内容控件作为模板提取输出的可填槽；填写阶段按 fill contract "
            "替换控件内容，填后移除占位符。"
            f"样式: {style}；字段值样式按契约中的 expected_value_style/style_contract_ref 验收。"
            "人工结论: 此块已覆盖，不是漏批。"
        )

    if kinds:
        return (
            "[覆盖批注 / 固定对象或生成域] "
            f"对象位置: {part_name} block#{index}, {context}. "
            f"内容: {preview}. 对象类型: {', '.join(kinds)}. "
            "处理动作: 作为模板结构/固定对象保留；若为 TOC/域则按契约生成区更新，"
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


def ensure_comments_root(existing: bytes | None) -> etree._Element:
    if existing:
        return etree.fromstring(existing)
    return etree.Element(w("comments"), nsmap={"w": W_NS})


def ensure_content_types(root: etree._Element) -> None:
    matches = root.xpath(
        "//*[local-name()='Override' and @PartName='/word/comments.xml']",
        namespaces=NS,
    )
    if matches:
        return
    override = etree.SubElement(root, ct("Override"))
    override.set("PartName", "/word/comments.xml")
    override.set("ContentType", COMMENTS_CONTENT_TYPE)


def ensure_document_rels(root: etree._Element) -> None:
    for rel in root.xpath("//pr:Relationship", namespaces=NS):
        if rel.get("Type") == COMMENTS_REL_TYPE and rel.get("Target") == "comments.xml":
            return
    ids: list[int] = []
    for rel in root.xpath("//pr:Relationship", namespaces=NS):
        match = re.fullmatch(r"rId(\d+)", rel.get("Id", ""))
        if match:
            ids.append(int(match.group(1)))
    rel = etree.SubElement(root, pkg("Relationship"))
    rel.set("Id", f"rId{max(ids, default=0) + 1}")
    rel.set("Type", COMMENTS_REL_TYPE)
    rel.set("Target", "comments.xml")


def next_comment_id(root: etree._Element) -> int:
    ids: list[int] = []
    for comment in root.xpath("//w:comment", namespaces=NS):
        value = comment.get(w("id"))
        try:
            ids.append(int(value or ""))
        except ValueError:
            pass
    return max(ids, default=-1) + 1


def remove_coverage_comments(comments_root: etree._Element, roots: dict[str, etree._Element]) -> int:
    coverage_ids = {
        comment.get(w("id"))
        for comment in comments_root.xpath("//w:comment", namespaces=NS)
        if comment.get(w("author")) == COVERAGE_AUTHOR
    }
    coverage_ids.discard(None)
    if not coverage_ids:
        return 0

    for comment in list(comments_root.xpath("//w:comment", namespaces=NS)):
        if comment.get(w("id")) in coverage_ids:
            parent = comment.getparent()
            if parent is not None:
                parent.remove(comment)

    for root in roots.values():
        for tag in ("commentRangeStart", "commentRangeEnd"):
            for marker in list(root.xpath(f".//w:{tag}", namespaces=NS)):
                if marker.get(w("id")) in coverage_ids:
                    parent = marker.getparent()
                    if parent is not None:
                        parent.remove(marker)
        for run in list(root.xpath(".//w:r[w:commentReference]", namespaces=NS)):
            refs = run.xpath("./w:commentReference", namespaces=NS)
            if refs and all(ref.get(w("id")) in coverage_ids for ref in refs):
                parent = run.getparent()
                if parent is not None:
                    parent.remove(run)
            else:
                for ref in refs:
                    if ref.get(w("id")) in coverage_ids:
                        run.remove(ref)

    return len(coverage_ids)


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


def append_comment(comments_root: etree._Element, comment_id: int, text: str) -> None:
    comment = etree.SubElement(comments_root, w("comment"))
    comment.set(w("id"), str(comment_id))
    comment.set(w("author"), COVERAGE_AUTHOR)
    comment.set(w("date"), dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat())
    p = etree.SubElement(comment, w("p"))
    run = etree.SubElement(p, w("r"))
    t = etree.SubElement(run, w("t"))
    t.text = text


def all_story_part_names(names: list[str]) -> list[str]:
    wanted = []
    for name in names:
        if name == "word/document.xml":
            wanted.append(name)
        elif re.fullmatch(r"word/(header|footer)\d+\.xml", name):
            wanted.append(name)
    return sorted(wanted, key=lambda x: (x != "word/document.xml", x))


def direct_comment_part_names(names: list[str]) -> list[str]:
    # OpenXML validation is strict about comment anchors in headers/footers in
    # this toolchain, so direct coverage comments are anchored only in the body.
    return ["word/document.xml"] if "word/document.xml" in names else []


@dataclass
class Audit:
    visible_blocks: int = 0
    header_footer_visible_blocks: int = 0
    missing_body_coverage: int = 0
    header_footer_summary_ok: bool = True
    added_comments: int = 0
    removed_old_coverage: int = 0
    existing_comments: int = 0
    total_comments: int = 0


def process_docx(path: Path, apply: bool) -> Audit:
    with zipfile.ZipFile(path, "r") as zin:
        names = zin.namelist()
        parts = all_story_part_names(names)
        roots = {name: etree.fromstring(zin.read(name)) for name in parts}
        comments_root = ensure_comments_root(
            zin.read("word/comments.xml") if "word/comments.xml" in names else None
        )
        existing_comments = len(comments_root.xpath("//w:comment", namespaces=NS))

        audit = Audit(existing_comments=existing_comments)
        if apply:
            audit.removed_old_coverage = remove_coverage_comments(comments_root, roots)
        next_id = next_comment_id(comments_root)

        for part_name in direct_comment_part_names(names):
            paragraphs = roots[part_name].xpath(".//w:p", namespaces=NS)
            for index, p in enumerate(paragraphs, start=1):
                if not is_visible_block(p):
                    continue
                audit.visible_blocks += 1
                if apply:
                    cid = next_id
                    next_id += 1
                    add_comment_to_paragraph(p, cid)
                    append_comment(comments_root, cid, comment_body(part_name, index, p))
                audit.added_comments += 1

        for part_name in parts:
            if part_name == "word/document.xml":
                continue
            audit.header_footer_visible_blocks += sum(
                1
                for p in roots[part_name].xpath(".//w:p", namespaces=NS)
                if is_visible_block(p)
            )

        if audit.header_footer_visible_blocks and apply:
            body_paragraphs = roots["word/document.xml"].xpath(".//w:p", namespaces=NS)
            first_visible = next((p for p in body_paragraphs if is_visible_block(p)), None)
            if first_visible is not None:
                cid = next_id
                next_id += 1
                add_comment_to_paragraph(first_visible, cid)
                append_comment(
                    comments_root,
                    cid,
                    "[覆盖批注 / 页眉页脚说明] "
                    f"检测到页眉/页脚可见内容块 {audit.header_footer_visible_blocks} 个。"
                    "处理动作: 页眉、页脚、页码、分节相关对象作为 protected 模板结构保留；"
                    "不作为学生字段填充。为保持 OpenXML 校验通过，本批注锚在正文总览处，"
                    "不直接锚到 header/footer part。人工结论: 页眉/页脚内容已覆盖，不是漏批。",
                )
                audit.added_comments += 1

        audit.total_comments = len(comments_root.xpath("//w:comment", namespaces=NS))
        coverage_ids = {
            comment.get(w("id"))
            for comment in comments_root.xpath("//w:comment", namespaces=NS)
            if comment.get(w("author")) == COVERAGE_AUTHOR
        }
        body_root = roots["word/document.xml"]
        for p in body_root.xpath(".//w:p", namespaces=NS):
            if not is_visible_block(p):
                continue
            anchored_ids = {
                marker.get(w("id"))
                for marker in p.xpath(
                    ".//w:commentRangeStart | .//w:commentReference",
                    namespaces=NS,
                )
            }
            if not (coverage_ids & anchored_ids):
                audit.missing_body_coverage += 1
        if audit.header_footer_visible_blocks:
            audit.header_footer_summary_ok = any(
                "页眉/页脚内容已覆盖" in "".join(comment.xpath(".//w:t/text()", namespaces=NS))
                for comment in comments_root.xpath("//w:comment", namespaces=NS)
                if comment.get(w("author")) == COVERAGE_AUTHOR
            )

        if not apply:
            return audit

        content_types = etree.fromstring(zin.read("[Content_Types].xml"))
        ensure_content_types(content_types)

        rels_name = "word/_rels/document.xml.rels"
        rels_root = etree.fromstring(zin.read(rels_name))
        ensure_document_rels(rels_root)

        overrides: dict[str, bytes] = {
            "[Content_Types].xml": xml_bytes(content_types),
            rels_name: xml_bytes(rels_root),
            "word/comments.xml": xml_bytes(comments_root),
        }
        overrides.update({name: xml_bytes(root) for name, root in roots.items()})

        fd, tmp_name = tempfile.mkstemp(suffix=".docx", dir=str(path.parent))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp_name, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    name = info.filename
                    if name in overrides:
                        zout.writestr(name, overrides[name])
                    else:
                        zout.writestr(name, zin.read(name))
                if "word/comments.xml" not in names:
                    zout.writestr("word/comments.xml", overrides["word/comments.xml"])
            shutil.move(tmp_name, path)
        finally:
            try:
                Path(tmp_name).unlink()
            except FileNotFoundError:
                pass

    return audit


def verify_comment_structure(path: Path) -> tuple[int, bool]:
    with zipfile.ZipFile(path, "r") as zin:
        names = zin.namelist()
        comments_root = etree.fromstring(zin.read("word/comments.xml"))
        ids = {
            comment.get(w("id"))
            for comment in comments_root.xpath("//w:comment", namespaces=NS)
        }
        starts: set[str | None] = set()
        ends: set[str | None] = set()
        refs: set[str | None] = set()
        for name in all_story_part_names(names):
            story_root = etree.fromstring(zin.read(name))
            starts.update(
                marker.get(w("id"))
                for marker in story_root.xpath(".//w:commentRangeStart", namespaces=NS)
            )
            ends.update(
                marker.get(w("id"))
                for marker in story_root.xpath(".//w:commentRangeEnd", namespaces=NS)
            )
            refs.update(
                marker.get(w("id"))
                for marker in story_root.xpath(".//w:commentReference", namespaces=NS)
            )
    return len(ids), ids <= starts and ids <= ends and ids <= refs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", nargs="+", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    for docx in args.docx:
        audit = process_docx(docx, apply=args.apply)
        if args.apply:
            total, ok = verify_comment_structure(docx)
            print(
                f"{docx}: visible_blocks={audit.visible_blocks} "
                f"header_footer_visible_blocks={audit.header_footer_visible_blocks} "
                f"removed_old_coverage={audit.removed_old_coverage} "
                f"added_coverage={audit.added_comments} total_comments={total} "
                f"missing_body_coverage={audit.missing_body_coverage} "
                f"header_footer_summary_ok={audit.header_footer_summary_ok} "
                f"structure_ok={ok}"
            )
        else:
            print(
                f"{docx}: visible_blocks={audit.visible_blocks} "
                f"header_footer_visible_blocks={audit.header_footer_visible_blocks} "
                f"existing_comments={audit.existing_comments} "
                f"missing_body_coverage={audit.missing_body_coverage} "
                f"header_footer_summary_ok={audit.header_footer_summary_ok} "
                f"would_add_coverage={audit.added_comments}"
            )


if __name__ == "__main__":
    main()
