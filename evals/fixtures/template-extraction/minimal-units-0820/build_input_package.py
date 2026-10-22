"""Build a standard prepare-template input package from 0820 minimal units."""

from __future__ import annotations

import argparse
import copy
import hashlib
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.yaml"

for prefix, uri in (
    ("w", W_NS),
    ("r", R_NS),
    ("w14", W14_NS),
    ("mc", MC_NS),
    ("rel", REL_NS),
):
    ET.register_namespace(prefix, uri)


def _q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _repo_root() -> Path:
    return ROOT.parents[3]


def _load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest.yaml must contain one mapping")
    return data


def _units_by_selector(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    units = manifest.get("units")
    if not isinstance(units, list):
        raise ValueError("manifest units must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in units:
        if not isinstance(item, dict):
            raise ValueError("each manifest unit must be a mapping")
        selector = item.get("selector")
        if not isinstance(selector, str) or not selector:
            raise ValueError("each manifest unit needs a selector")
        if selector in result:
            raise ValueError(f"duplicate unit selector: {selector}")
        result[selector] = item
    return result


def _selected_units(manifest: dict[str, Any], value: str) -> list[dict[str, Any]]:
    selectors = _units_by_selector(manifest)
    requested = [item.strip() for item in value.split(",") if item.strip()]
    if requested == ["all"]:
        requested = [str(item["selector"]) for item in manifest["units"]]
    if not requested:
        raise ValueError("--units must name at least one selector")
    duplicates = sorted({item for item in requested if requested.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate unit selector(s): {', '.join(duplicates)}")
    unknown = sorted(set(requested) - set(selectors))
    if unknown:
        known = ", ".join(selectors)
        raise ValueError(f"unknown unit selector(s): {', '.join(unknown)}; known: {known}")
    return [selectors[item] for item in requested]


def _fixture_path(unit: dict[str, Any], key: str) -> Path:
    value = unit.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"unit {unit.get('selector')} has no {key}")
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"unit path escapes fixture root: {value}") from error
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _hash_check(path: Path, expected: object) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{path} has no declared sha256")
    actual = _sha256_file(path)
    if actual != expected:
        raise ValueError(f"{path} sha256 mismatch: expected {expected}, got {actual}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_docx_parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _write_docx_parts(path: Path, parts: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(parts):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, parts[name])


def _xml(parts: dict[str, bytes], name: str) -> ET.Element:
    try:
        return ET.fromstring(parts[name])
    except (KeyError, ET.ParseError) as error:
        raise ValueError(f"DOCX part is missing or invalid XML: {name}") from error


def _serialize(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _validate_docx_package(path: Path) -> None:
    required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"{path} is missing required DOCX parts: {missing}")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ValueError(f"{path} contains a corrupt ZIP member: {corrupt}")
        for name in sorted(names):
            if name.endswith((".xml", ".rels")):
                ET.fromstring(archive.read(name))


def _body_children_for_import(docx: Path) -> list[ET.Element]:
    with zipfile.ZipFile(docx) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(_q(W_NS, "body"))
    if body is None:
        raise ValueError(f"{docx} has no document body")

    imported: list[ET.Element] = []
    for child in list(body):
        if child.tag == _q(W_NS, "sectPr"):
            continue
        if child.tag not in {_q(W_NS, "p"), _q(W_NS, "tbl")}:
            raise ValueError(
                f"{docx} has unsupported direct body object {child.tag}; "
                "only top-level paragraphs and tables can be combined"
            )
        imported.append(copy.deepcopy(child))
    if not imported:
        raise ValueError(f"{docx} has no importable body objects")
    return imported


def _combine_docx(units: Sequence[dict[str, Any]], output_docx: Path) -> None:
    first = _fixture_path(units[0], "source_docx")
    shutil.copyfile(first, output_docx)
    parts = _read_docx_parts(output_docx)
    document = _xml(parts, "word/document.xml")
    body = document.find(_q(W_NS, "body"))
    if body is None:
        raise ValueError(f"{output_docx} has no document body")
    for unit in units[1:]:
        source = _fixture_path(unit, "source_docx")
        final_section = body.find(_q(W_NS, "sectPr"))
        insert_index = list(body).index(final_section) if final_section is not None else len(body)
        for offset, child in enumerate(_body_children_for_import(source)):
            body.insert(insert_index + offset, child)
    parts["word/document.xml"] = _serialize(document)
    _write_docx_parts(output_docx, parts)
    _validate_docx_package(output_docx)


def _combine_pdf(paths: Sequence[Path], output_pdf: Path) -> None:
    if len(paths) == 1:
        shutil.copyfile(paths[0], output_pdf)
        return
    executable = shutil.which("pdfunite")
    if executable is None:
        raise RuntimeError(
            "pdfunite is required to build a multi-unit PDF requirements file"
        )
    completed = subprocess.run(
        [executable, *(str(path) for path in paths), str(output_pdf)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "pdfunite failed")


def _copy_field_registry(manifest: dict[str, Any], output: Path) -> None:
    registry = manifest.get("field_registry")
    if not isinstance(registry, dict) or not isinstance(registry.get("path"), str):
        raise ValueError("manifest field_registry.path is required")
    source = (ROOT / registry["path"]).resolve()
    source.relative_to(_repo_root())
    if not source.is_file():
        raise FileNotFoundError(source)
    _hash_check(source, registry.get("sha256"))
    shutil.copyfile(source, output)


def _write_selected_manifest(
    *,
    manifest: dict[str, Any],
    units: Sequence[dict[str, Any]],
    output: Path,
    input_dir: Path,
) -> None:
    payload = {
        "schema_version": "docfit-template-extraction-selected-input/v1",
        "fixture_id": manifest["fixture_id"],
        "source_manifest": str(MANIFEST.relative_to(_repo_root())),
        "selected_units": [
            {
                "unit_id": unit["unit_id"],
                "selector": unit["selector"],
                "label_zh": unit["label_zh"],
                "ordinal": unit["ordinal"],
                "source_docx_sha256": unit["docx_sha256"],
                "source_pdf_sha256": unit["pdf_sha256"],
            }
            for unit in units
        ],
        "inputs": {
            "school_template": "input/school-template.docx",
            "school_requirements": "input/school-requirements.pdf",
            "field_registry": "input/field-registry.yaml",
            "school_template_sha256": _sha256_file(input_dir / "school-template.docx"),
            "school_requirements_sha256": _sha256_file(
                input_dir / "school-requirements.pdf"
            ),
            "field_registry_sha256": _sha256_file(input_dir / "field-registry.yaml"),
        },
        "trust_boundary": manifest["trust_boundary"],
    }
    output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def build_input_package(*, units_value: str, output_root: Path, force: bool) -> Path:
    manifest = _load_manifest()
    units = _selected_units(manifest, units_value)
    if output_root.exists():
        if not force:
            raise FileExistsError(f"{output_root} already exists; pass --force to replace it")
        shutil.rmtree(output_root)
    input_dir = output_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    docx_paths = [_fixture_path(unit, "source_docx") for unit in units]
    pdf_paths = [_fixture_path(unit, "source_pdf") for unit in units]
    for unit, docx, pdf in zip(units, docx_paths, pdf_paths, strict=True):
        _hash_check(docx, unit["docx_sha256"])
        _hash_check(pdf, unit["pdf_sha256"])

    if len(units) == 1:
        shutil.copyfile(docx_paths[0], input_dir / "school-template.docx")
    else:
        _combine_docx(units, input_dir / "school-template.docx")
    _combine_pdf(pdf_paths, input_dir / "school-requirements.pdf")
    _copy_field_registry(manifest, input_dir / "field-registry.yaml")
    _write_selected_manifest(
        manifest=manifest,
        units=units,
        output=input_dir / "selected-units.yaml",
        input_dir=input_dir,
    )
    return input_dir


def _prepare_template_command(input_dir: Path) -> str:
    run_root = input_dir.parent / "run"
    return (
        "uv run docfit prepare-template "
        f"--school-template {input_dir / 'school-template.docx'} "
        f"--school-requirements {input_dir / 'school-requirements.pdf'} "
        f"--field-registry {input_dir / 'field-registry.yaml'} "
        f"--output {run_root} "
        "--until unit-boundary"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a standard prepare-template input package from 0820 units."
    )
    parser.add_argument(
        "--units",
        required=True,
        help="Comma-separated selectors, e.g. 01-cover,03-toc, or all.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print a prepare-template --until unit-boundary command after building.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        input_dir = build_input_package(
            units_value=args.units,
            output_root=args.output,
            force=args.force,
        )
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(input_dir)
    if args.print_command:
        print(_prepare_template_command(input_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
