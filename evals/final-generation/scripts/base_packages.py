"""Prepare and validate final-generation base input packages.

This script intentionally stays below end-to-end generation. It prepares:

- three student content packages
- three school template packages

Then it can validate package hashes, Registry bindings, runtime Fill Contract
loading, and all 3x3 placement combinations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from docfit.app.student_content_fill import FinalGenerationRequest, prepare_final_generation
from docfit.content.placement import build_placement, load_fill_contract
from docfit.content.student import build_student_inventory
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.inspection import inspect_document
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import ToolFailure

FIELD_ID_MAP = {
    "body.heading.level1": "body.heading.outline1",
    "body.heading.level2": "body.heading.outline2",
    "body.heading.level3": "body.heading.outline3",
    "body.heading.level4": "body.heading.outline4",
    "body.heading.level5": "body.heading.outline5",
}

STUDENT_IDS = ("student-001", "student-002", "student-003")
SCHOOL_IDS = ("hunau-undergraduate", "njau-undergraduate", "pku-graduate")
TOP_PARAGRAPH = re.compile(r"/body/p\[@paraId=[0-9A-Fa-f]+\]")
TOP_TABLE = re.compile(r"/body/tbl\[\d+\]")


class CheckFailure(Exception):
    """A base package failed deterministic validation."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("temp/final-generation-base-packages-20260816"),
        help="Base package output root, relative to the repository by default.",
    )
    parser.add_argument("--prepare", action="store_true", help="Prepare the base packages.")
    parser.add_argument("--check", action="store_true", help="Validate the base packages.")
    parser.add_argument(
        "--runtime-inventory",
        action="store_true",
        help="Also prepare one runtime snapshot per student to confirm transport IDs.",
    )
    args = parser.parse_args(argv)

    if not args.prepare and not args.check:
        parser.error("select at least one of --prepare or --check")

    repo = repository_root()
    root = resolve_inside_repo(repo, args.root)
    if args.prepare:
        prepare_packages(repo, root)
    if args.check:
        report = check_packages(repo, root, runtime_inventory=args.runtime_inventory)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["status"] == "PASS" else 1
    return 0


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_inside_repo(repo: Path, path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (repo / path).resolve()
    if not resolved.is_relative_to(repo):
        raise CheckFailure(f"path is outside repository: {path}")
    return resolved


def prepare_packages(repo: Path, root: Path) -> None:
    safe_reset_output(repo, root)
    registry_path = repo / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
    registry = read_yaml(registry_path)
    student_summaries = [
        prepare_student_package(repo, root, registry_path, registry, student_id)
        for student_id in STUDENT_IDS
    ]
    school_summaries = [
        prepare_school_package(repo, root, registry_path, registry, school_id)
        for school_id in SCHOOL_IDS
    ]
    (root / "README.md").write_text(root_readme(), encoding="utf-8")
    write_json(
        root / "package-summary.json",
        {
            "schema_version": "docfit-final-generation-base-package-summary/v1",
            "created_at": now_utc(),
            "registry": registry_identity(registry_path, registry),
            "students": student_summaries,
            "schools": school_summaries,
        },
    )


def safe_reset_output(repo: Path, root: Path) -> None:
    temp = (repo / "temp").resolve()
    if root.exists():
        if not root.is_relative_to(temp) or not root.name.startswith(
            "final-generation-base-packages"
        ):
            raise CheckFailure(f"refusing to reset unexpected output root: {root}")
        make_writable(root)
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def prepare_student_package(
    repo: Path,
    root: Path,
    registry_path: Path,
    registry: dict[str, Any],
    student_id: str,
) -> dict[str, Any]:
    package_root = root / "students" / student_id
    package_root.mkdir(parents=True, exist_ok=True)
    expected_source_sha256 = expected_student_source_sha256(repo, student_id)
    source_path = find_student_source(repo, student_id, expected_source_sha256)
    copy_file(source_path, package_root / "student.docx")
    copy_file(registry_path, package_root / "content-fields.yaml")
    model = convert_student_gold(repo, registry_path, registry, student_id)
    write_json(package_root / "student-content.json", model)
    (package_root / "README.md").write_text(student_readme(student_id), encoding="utf-8")
    manifest = package_manifest(
        package_id=student_id,
        package_type="student_content",
        package_root=package_root,
        files=("student.docx", "student-content.json", "content-fields.yaml", "README.md"),
        extra={
            "student_id": student_id,
            "source_sha256": model["source_sha256"],
            "registry": model["registry"],
            "student_content_schema_version": model["schema_version"],
            "student_content_status": model["status"],
            "source_gold_status": model["lineage"]["source_gold_status"],
        },
    )
    write_json(package_root / "manifest.json", manifest)
    return {
        "student_id": student_id,
        "source_sha256": model["source_sha256"],
        "item_count": len(model["items"]),
        "field_result_count": len(model["field_results"]),
        "source_object_count": model["source_coverage"]["source_object_count"],
        "all_source_objects_accounted_for": model["source_coverage"][
            "all_source_objects_accounted_for"
        ],
        "unsupported_source_object_count": len(
            model["source_coverage"]["unsupported_source_object_ids"]
        ),
    }


def prepare_school_package(
    repo: Path,
    root: Path,
    registry_path: Path,
    registry: dict[str, Any],
    school_id: str,
) -> dict[str, Any]:
    package_root = root / "schools" / school_id
    package_root.mkdir(parents=True, exist_ok=True)
    source = school_source(repo, school_id)
    copy_file(source["template"], package_root / "final-template.docx")
    copy_file(source["contract"], package_root / "fill-contract.yaml")
    copy_file(registry_path, package_root / "content-fields.yaml")
    contract = read_yaml(package_root / "fill-contract.yaml")
    template_sha256 = sha256_file(package_root / "final-template.docx")
    if contract.get("template_sha256") != template_sha256:
        raise CheckFailure(f"{school_id}: Fill Contract does not bind copied template")
    (package_root / "README.md").write_text(
        school_readme(school_id, str(contract.get("status"))),
        encoding="utf-8",
    )
    manifest = package_manifest(
        package_id=school_id,
        package_type="school_template",
        package_root=package_root,
        files=("final-template.docx", "fill-contract.yaml", "content-fields.yaml", "README.md"),
        extra={
            "school_id": school_id,
            "template_sha256": template_sha256,
            "registry": registry_identity(registry_path, registry),
            "fill_contract_schema_version": contract.get("schema_version"),
            "fill_contract_status": contract.get("status"),
            "slot_count": len(contract.get("slots") or []),
            "style_count": len(contract.get("styles") or []),
            "region_count": len(contract.get("regions") or []),
            "note": (
                "Candidate template package for base-package and placement validation. "
                "Contract status is preserved."
            ),
        },
    )
    write_json(package_root / "manifest.json", manifest)
    return {
        "school_id": school_id,
        "template_sha256": template_sha256,
        "fill_contract_status": contract.get("status"),
        "slot_count": len(contract.get("slots") or []),
        "style_count": len(contract.get("styles") or []),
        "region_count": len(contract.get("regions") or []),
    }


def convert_student_gold(
    repo: Path,
    registry_path: Path,
    registry: dict[str, Any],
    student_id: str,
) -> dict[str, Any]:
    asset_root = repo / "temp/manual-gold-preparation/gold/20-student-assets" / student_id
    manifest = read_yaml(asset_root / "manifest.yaml")
    gold = read_json(asset_root / "student-content.gold.json")
    expected_source_sha256 = manifest["student_source"]["sha256"]
    source_path = find_student_source(repo, student_id, expected_source_sha256)
    inventory = current_runtime_inventory(source_path)
    source_sha256 = sha256_file(source_path)
    if source_sha256 != expected_source_sha256:
        raise CheckFailure(
            f"{student_id}: source sha mismatch {source_sha256} != {expected_source_sha256}"
        )
    registry_types = {
        str(field["field_id"]): str(field.get("content_type", "text"))
        for field in registry["fields"]
    }
    registry_fields = set(registry_types)
    locator_map = inventory_locator_map(inventory)
    items: list[dict[str, Any]] = []
    missing_transport: list[str] = []
    for raw in gold.get("items") or []:
        if not isinstance(raw, dict):
            continue
        refs = [
            dict(ref)
            for ref in raw.get("source_object_refs") or []
            if isinstance(ref, dict)
        ]
        source_locators = [
            str(ref["source_locator"])
            for ref in refs
            if isinstance(ref.get("source_locator"), str)
        ]
        source_object_ids = [
            str(ref["object_id"])
            for ref in refs
            if isinstance(ref.get("object_id"), str)
        ]
        field_id = FIELD_ID_MAP.get(str(raw.get("field_id")), str(raw.get("field_id")))
        status = (
            "classified"
            if raw.get("classification_status") == "registered"
            else str(raw.get("classification_status"))
        )
        if status == "classified" and field_id not in registry_fields:
            raise CheckFailure(f"{student_id}: field is not in Registry v0.5: {field_id}")
        physical_type = content_physical_type(field_id, refs, registry_types)
        transport_id, transport_locator = transport_source(source_locators, source_object_ids, locator_map)
        item = {
            "content_id": raw.get("content_id"),
            "source_content_id": raw.get("content_id"),
            "field_id": field_id,
            "classification_status": status,
            "content_type": registry_types.get(field_id, raw.get("content_type") or physical_type),
            "physical_type": physical_type,
            "value": item_value(raw, physical_type),
            "source_order": dict(raw.get("source_order") or {}),
            "source_object_ids": source_object_ids,
            "source_locators": source_locators,
            "content_ref": {
                "student_document_sha256": source_sha256,
                "source_object_ids": source_object_ids,
                "source_locators": source_locators,
            },
            "parent_content_id": raw.get("parent_content_id"),
            "confidence": 1.0,
            "note": "Converted from accepted extraction gold for final-generation base package.",
        }
        if refs:
            item["source_object_refs"] = refs
        if raw.get("source_occurrences") is not None:
            item["source_occurrences"] = raw["source_occurrences"]
        if raw.get("source_span") is not None:
            item["source_span"] = raw["source_span"]
        if field_id != "body.chapters" and transport_id and transport_locator:
            item["transport_source_object_id"] = transport_id
            item["transport_source_locator"] = transport_locator
        elif field_id.startswith("body.") and field_id != "body.chapters":
            missing_transport.append(str(raw.get("content_id")))
        items.append(item)
    if missing_transport:
        raise CheckFailure(
            f"{student_id}: body items missing transport source: {missing_transport[:20]}"
        )
    items.sort(key=lambda item: (item["source_order"]["block"], item["source_order"]["inline"]))
    return {
        "schema_version": "docfit-student-content-model/v2",
        "status": "READY",
        "source_sha256": source_sha256,
        "registry": registry_identity(registry_path, registry),
        "items": items,
        "field_results": convert_field_results(gold),
        "relations": caption_relations(items),
        "source_coverage": convert_coverage(gold),
        "lineage": {
            "source_gold_schema_version": gold.get("schema_version"),
            "source_gold_id": gold.get("gold_id"),
            "source_gold_revision": gold.get("gold_revision") or manifest.get("gold_revision"),
            "source_gold_status": gold.get("status"),
            "source_manifest": str((asset_root / "manifest.yaml").relative_to(repo)),
            "conversion": (
                "accepted extraction gold -> final-generation Student Content Model v2; "
                "body.heading.levelN migrated to body.heading.outlineN; Registry rebound to v0.5; "
                "transport object IDs rebound from the current runtime inventory by source locator"
            ),
        },
        "privacy": "task_local_contains_student_content",
    }


def current_runtime_inventory(source_path: Path) -> dict[str, Any]:
    scratch = Path(
        tempfile.mkdtemp(
            prefix=f".{source_path.stem}-inventory-",
            dir=source_path.parent,
        )
    )
    try:
        source_copy = scratch / source_path.name
        shutil.copy2(source_path, source_copy)
        inspection = inspect_document(source_copy, OfficeCliAdapter())
        return build_student_inventory(inspection, source_docx=source_copy)
    finally:
        if scratch.exists():
            make_writable(scratch)
            shutil.rmtree(scratch)


def convert_field_results(gold: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for raw in gold.get("field_results") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if isinstance(item.get("field_id"), str):
            item["field_id"] = FIELD_ID_MAP.get(item["field_id"], item["field_id"])
        results.append(item)
    return results


def caption_relations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item["content_id"]): item for item in items if isinstance(item.get("content_id"), str)}
    relations = []
    for item in items:
        parent_id = item.get("parent_content_id")
        parent = by_id.get(str(parent_id))
        field_id = item.get("field_id")
        parent_field_id = parent.get("field_id") if isinstance(parent, dict) else None
        if (
            isinstance(parent_id, str)
            and isinstance(field_id, str)
            and field_id.endswith(".caption")
            and parent_field_id in {"body.figure", "body.table"}
        ):
            relations.append(
                {
                    "relation_type": "caption_of",
                    "source_content_id": item["content_id"],
                    "target_content_id": parent_id,
                    "confidence": 1.0,
                    "note": "Preserved from accepted extraction gold parent_content_id.",
                }
            )
    return relations


def convert_coverage(gold: dict[str, Any]) -> dict[str, Any]:
    coverage = gold.get("coverage") or {}
    buckets = {
        "mapped_source_object_ids": [],
        "covered_dependency_object_ids": [],
        "layout_only_source_object_ids": [],
        "unsupported_source_object_ids": [],
    }
    for obj in coverage.get("objects") or []:
        if not isinstance(obj, dict) or not isinstance(obj.get("object_id"), str):
            continue
        status = obj.get("status")
        if status == "mapped":
            buckets["mapped_source_object_ids"].append(obj["object_id"])
        elif status == "covered_dependency":
            buckets["covered_dependency_object_ids"].append(obj["object_id"])
        elif status == "excluded":
            buckets["layout_only_source_object_ids"].append(obj["object_id"])
        else:
            buckets["unsupported_source_object_ids"].append(obj["object_id"])
    classifications = Counter()
    for item in gold.get("items") or []:
        if isinstance(item, dict):
            status = item.get("classification_status")
            classifications["classified" if status == "registered" else str(status)] += 1
    return {
        "source_object_count": coverage.get("object_count"),
        **{key: sorted(set(value)) for key, value in buckets.items()},
        "content_item_classifications": dict(sorted(classifications.items())),
        "all_source_objects_accounted_for": coverage.get("all_objects_accounted_for") is True,
        "gold_status_counts": dict(coverage.get("status_counts") or {}),
        "gold_unresolved_count": coverage.get("unresolved_count"),
    }


def content_physical_type(
    field_id: str,
    refs: list[dict[str, Any]],
    registry_types: dict[str, str],
) -> str:
    content_type = registry_types.get(field_id, "text")
    if content_type in {"image", "table", "equation", "section"}:
        return content_type
    if any("/image[" in str(ref.get("source_locator", "")) for ref in refs):
        return "image"
    return "text"


def item_value(raw: dict[str, Any], physical_type: str) -> str | None:
    if physical_type in {"image", "table", "equation"}:
        return None
    for key in ("normalized_value", "observed_value"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
    texts = [
        str(occurrence["observed_text"])
        for occurrence in raw.get("source_occurrences") or []
        if isinstance(occurrence, dict) and isinstance(occurrence.get("observed_text"), str)
    ]
    return "\n".join(texts) if texts else None


def transport_source(
    source_locators: list[str],
    source_object_ids: list[str],
    locator_map: dict[str, tuple[str, str]],
) -> tuple[str | None, str | None]:
    if not source_locators:
        return None, None
    locator = source_locators[0]
    mapped = locator_map.get(top_locator(locator)) or locator_map.get(locator)
    if mapped:
        return mapped
    return (source_object_ids[0] if source_object_ids else None), top_locator(locator)


def top_locator(locator: str) -> str:
    table = TOP_TABLE.match(locator)
    if table:
        return table.group(0)
    paragraph = TOP_PARAGRAPH.match(locator)
    if paragraph:
        return paragraph.group(0)
    return locator


def inventory_locator_map(inventory: dict[str, Any]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for obj in inventory.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        locator = obj.get("source_locator")
        ref = obj.get("source_object_ref")
        object_id = ref.get("object_id") if isinstance(ref, dict) else None
        if isinstance(locator, str) and isinstance(object_id, str):
            result.setdefault(locator, (object_id, locator))
    for item in inventory.get("content_items") or []:
        if not isinstance(item, dict):
            continue
        transport_id = item.get("transport_source_object_id")
        transport_locator = item.get("transport_source_locator")
        if not isinstance(transport_id, str) or not isinstance(transport_locator, str):
            continue
        for locator in item.get("source_locators") or []:
            if isinstance(locator, str):
                result.setdefault(locator, (transport_id, transport_locator))
    return result


def check_packages(repo: Path, root: Path, *, runtime_inventory: bool) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    students = []
    schools = []
    combinations = []
    runtime_checks = []

    for student_id in STUDENT_IDS:
        try:
            students.append(check_student_package(root / "students" / student_id))
        except Exception as error:  # noqa: BLE001 - report all validation failures.
            failures.append({"scope": student_id, "code": "student_package_failed", "message": str(error)})
    for school_id in SCHOOL_IDS:
        try:
            schools.append(check_school_package(root / "schools" / school_id))
        except Exception as error:  # noqa: BLE001 - report all validation failures.
            failures.append({"scope": school_id, "code": "school_package_failed", "message": str(error)})
    if not failures:
        for student_id in STUDENT_IDS:
            for school_id in SCHOOL_IDS:
                try:
                    combinations.append(check_combination(root, student_id, school_id))
                except Exception as error:  # noqa: BLE001 - report exact failed pairing.
                    failures.append(
                        {
                            "scope": f"{student_id} x {school_id}",
                            "code": "placement_combination_failed",
                            "message": str(error),
                        }
                    )
    if runtime_inventory and not failures:
        for student_id in STUDENT_IDS:
            try:
                runtime_checks.append(check_runtime_inventory(repo, root, student_id))
            except Exception as error:  # noqa: BLE001
                failures.append(
                    {
                        "scope": f"{student_id} runtime inventory",
                        "code": "runtime_inventory_failed",
                        "message": str(error),
                    }
                )
    report = {
        "schema_version": "docfit-final-generation-base-package-check-report/v1",
        "status": "PASS" if not failures else "FAIL",
        "checked_at": now_utc(),
        "root": str(root),
        "students": students,
        "schools": schools,
        "placement_combinations": combinations,
        "runtime_inventory_checks": runtime_checks,
        "failures": failures,
        "summary": {
            "student_package_count": len(students),
            "school_package_count": len(schools),
            "placement_combination_count": len(combinations),
            "runtime_inventory_check_count": len(runtime_checks),
        },
    }
    write_json(root / "check-report.json", report)
    return report


def check_student_package(root: Path) -> dict[str, Any]:
    require_files(root, ("student.docx", "student-content.json", "content-fields.yaml", "manifest.json"))
    check_manifest(root)
    registry = FieldRegistrySnapshot.load(root / "content-fields.yaml")
    student = read_json(root / "student-content.json")
    assert_true(student.get("schema_version") == "docfit-student-content-model/v2", "invalid schema")
    assert_true(student.get("status") == "READY", "student content is not READY")
    assert_true(student.get("source_sha256") == sha256_file(root / "student.docx"), "source sha mismatch")
    assert_true(student.get("registry") == registry.identity(), "registry binding mismatch")
    items = student.get("items")
    assert_true(isinstance(items, list) and items, "items missing")
    content_ids = [item.get("content_id") for item in items if isinstance(item, dict)]
    assert_true(len(content_ids) == len(set(content_ids)), "content_id duplicate")
    orders = [source_order(item) for item in items if isinstance(item, dict)]
    assert_true(orders == sorted(orders) and len(orders) == len(set(orders)), "source_order is not strict")
    registry_field_ids = {field["field_id"] for field in registry.fields}
    item_field_ids = {
        item.get("field_id")
        for item in items
        if isinstance(item, dict) and item.get("classification_status") == "classified"
    }
    assert_true(item_field_ids <= registry_field_ids, "item field outside Registry")
    result_field_ids = {
        result.get("field_id")
        for result in student.get("field_results") or []
        if isinstance(result, dict)
    }
    assert_true(result_field_ids == registry_field_ids, "field_results do not cover Registry v0.5")
    missing_transport = [
        str(item.get("content_id"))
        for item in items
        if isinstance(item, dict)
        and item.get("classification_status") == "classified"
        and isinstance(item.get("field_id"), str)
        and str(item["field_id"]).startswith("body.")
        and item.get("field_id") != "body.chapters"
        and (
            not isinstance(item.get("transport_source_object_id"), str)
            or not isinstance(item.get("transport_source_locator"), str)
        )
    ]
    assert_true(not missing_transport, f"body items missing transport: {missing_transport[:10]}")
    coverage = student.get("source_coverage")
    assert_true(isinstance(coverage, dict), "source_coverage missing")
    assert_true(coverage.get("all_source_objects_accounted_for") is True, "source coverage incomplete")
    assert_true(not coverage.get("unsupported_source_object_ids"), "unsupported source objects present")
    return {
        "student_id": root.name,
        "status": "PASS",
        "source_sha256": student.get("source_sha256"),
        "item_count": len(items),
        "field_result_count": len(student.get("field_results") or []),
        "source_object_count": coverage.get("source_object_count"),
        "all_source_objects_accounted_for": coverage.get("all_source_objects_accounted_for"),
    }


def check_school_package(root: Path) -> dict[str, Any]:
    require_files(root, ("final-template.docx", "fill-contract.yaml", "content-fields.yaml", "manifest.json"))
    check_manifest(root)
    registry = FieldRegistrySnapshot.load(root / "content-fields.yaml")
    contract = load_fill_contract(root / "fill-contract.yaml")
    assert_true(contract.get("schema_version") == "docfit-template-fill-contract/v2", "invalid contract schema")
    assert_true(contract.get("template_sha256") == sha256_file(root / "final-template.docx"), "template binding mismatch")
    assert_true(
        all(
            contract.get("field_registry_ref", {}).get(key) == registry.identity()[key]
            for key in ("registry_id", "registry_version", "sha256")
        ),
        "registry binding mismatch",
    )
    return {
        "school_id": root.name,
        "status": "PASS",
        "fill_contract_status": contract.get("status"),
        "template_sha256": contract.get("template_sha256"),
        "slot_count": len(contract.get("slots") or []),
        "style_count": len(contract.get("styles") or []),
        "region_count": len(contract.get("regions") or []),
        "style_contract_set_digest": contract.get("style_contract_set_digest"),
    }


def check_combination(root: Path, student_id: str, school_id: str) -> dict[str, Any]:
    student_root = root / "students" / student_id
    school_root = root / "schools" / school_id
    registry = FieldRegistrySnapshot.load(school_root / "content-fields.yaml")
    student = read_json(student_root / "student-content.json")
    contract = load_fill_contract(school_root / "fill-contract.yaml")
    placement = build_placement(
        student_content=student,
        contract=contract,
        registry=registry,
        template_docx=school_root / "final-template.docx",
    )
    return {
        "student_id": student_id,
        "school_id": school_id,
        "status": "PASS",
        "placement_status": placement.get("status"),
        "partial_reasons": placement.get("partial_reasons"),
        "operation_count": len(placement.get("operations") or []),
        "missing_required_count": len(placement.get("missing_required") or []),
    }


def check_runtime_inventory(repo: Path, root: Path, student_id: str) -> dict[str, Any]:
    student_root = root / "students" / student_id
    school_root = root / "schools/njau-undergraduate"
    output = Path(
        tempfile.mkdtemp(
            prefix=f".{root.name}-{student_id}-runtime-",
            dir=root.parent,
        )
    )
    try:
        prepared = prepare_final_generation(
            FinalGenerationRequest(
                source_docx=student_root / "student.docx",
                student_content=student_root / "student-content.json",
                template_docx=school_root / "final-template.docx",
                fill_contract=school_root / "fill-contract.yaml",
                field_registry=school_root / "content-fields.yaml",
                output_directory=output,
            )
        )
        student = read_json(student_root / "student-content.json")
        inventory_ids = {
            str(item["source_object_ref"]["object_id"])
            for item in prepared.inventory.get("objects", [])
            if isinstance(item, dict)
            and isinstance(item.get("source_object_ref"), dict)
            and isinstance(item["source_object_ref"].get("object_id"), str)
        }
        transport_ids = {
            str(item["transport_source_object_id"])
            for item in student.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("transport_source_object_id"), str)
        }
        missing = sorted(transport_ids - inventory_ids)
        assert_true(not missing, f"transport IDs absent from runtime inventory: {missing[:10]}")
        return {
            "student_id": student_id,
            "status": "PASS",
            "source_sha256": prepared.source_sha256,
            "transport_source_id_count": len(transport_ids),
            "runtime_inventory_object_count": len(inventory_ids),
        }
    finally:
        if output.exists():
            make_writable(output)
            shutil.rmtree(output)


def require_files(root: Path, names: tuple[str, ...]) -> None:
    for name in names:
        assert_true((root / name).is_file(), f"missing file: {name}")


def check_manifest(root: Path) -> None:
    manifest = read_json(root / "manifest.json")
    files = manifest.get("files")
    assert_true(isinstance(files, dict), "manifest.files missing")
    for name, meta in files.items():
        path = root / str(name)
        assert_true(path.is_file(), f"manifest file missing: {name}")
        assert_true(isinstance(meta, dict), f"manifest metadata invalid: {name}")
        assert_true(meta.get("sha256") == sha256_file(path), f"sha mismatch: {name}")
        assert_true(meta.get("bytes") == path.stat().st_size, f"size mismatch: {name}")


def source_order(item: dict[str, Any]) -> tuple[int, int]:
    order = item.get("source_order")
    if not isinstance(order, dict):
        raise CheckFailure("source_order missing")
    block = order.get("block")
    inline = order.get("inline")
    if (
        not isinstance(block, int)
        or isinstance(block, bool)
        or not isinstance(inline, int)
        or isinstance(inline, bool)
    ):
        raise CheckFailure("source_order invalid")
    return block, inline


def expected_student_source_sha256(repo: Path, student_id: str) -> str:
    manifest = read_yaml(
        repo
        / "temp/manual-gold-preparation/gold/20-student-assets"
        / student_id
        / "manifest.yaml"
    )
    return str(manifest["student_source"]["sha256"])


def find_student_source(repo: Path, student_id: str, expected_sha256: str) -> Path:
    candidates = student_source_candidates(repo, student_id)
    existing = [candidate for candidate in candidates if candidate.is_file()]
    for candidate in existing:
        if sha256_file(candidate) == expected_sha256:
            return candidate
    details = ", ".join(
        f"{candidate}={sha256_file(candidate)}" for candidate in existing[:6]
    )
    raise CheckFailure(
        f"{student_id}: no source candidate matches manifest sha {expected_sha256}; {details}"
    )


def student_source_candidates(repo: Path, student_id: str) -> tuple[Path, ...]:
    suffix = student_id.removeprefix("student-")
    worktree_root = repo.parent
    return (
        worktree_root
        / "template-extraction"
        / "temp/external-docfit-v3-220455/inputs/students"
        / f"real-student-{suffix}"
        / "raw/source_document.docx",
        worktree_root
        / "user-content-extraction"
        / "temp/manual-gold-preparation/gold/00-inputs/students"
        / f"student-{suffix}__source-thesis.docx",
        Path("/Volumes/ExtSSD2601/Docfit/temp/manual-gold-preparation/gold/00-inputs/students")
        / f"student-{suffix}__source-thesis.docx",
        repo / f"temp/manual-gold-preparation/student-content-real-student-{suffix}.docx",
    )


def school_source(repo: Path, school_id: str) -> dict[str, Any]:
    mapping = {
        "hunau-undergraduate": "student-001-hunau",
        "njau-undergraduate": "student-001-njau",
        "pku-graduate": "student-001-pku",
    }
    root = repo / f"temp/final-generation-e2e-20260814/{mapping[school_id]}/prepared-inputs"
    return {
        "template": root / "template.docx",
        "contract": root / "fill-contract.repaired.yaml",
    }


def package_manifest(
    *,
    package_id: str,
    package_type: str,
    package_root: Path,
    files: tuple[str, ...],
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "docfit-final-generation-base-package/v1",
        "package_id": package_id,
        "package_type": package_type,
        "created_at": now_utc(),
        "files": {name: file_meta(package_root / name) for name in files},
        **extra,
    }


def root_readme() -> str:
    return """# final-generation base packages

This directory contains base input packages only. It does not contain
candidate.docx, final.docx, or E2E expected output.

Student packages live under students/<student-id>/ and provide:
- student.docx
- student-content.json
- content-fields.yaml
- manifest.json

School packages live under schools/<school-id>/ and provide:
- final-template.docx
- fill-contract.yaml
- content-fields.yaml
- manifest.json

To create a combination, take student.docx and student-content.json from one
student package, final-template.docx and fill-contract.yaml from one school
package, and use the package-local content-fields.yaml. These packages validate
input binding and placement compatibility. Full document generation is the next
layer.

The school Fill Contract status is preserved. The current school packages are
candidate template packages for base-package and placement validation; they are
not accepted final template contracts.
"""


def student_readme(student_id: str) -> str:
    return f"""# {student_id} student base package

Purpose: final-generation student content input.

Files:
- student.docx: original student thesis document.
- student-content.json: docfit-student-content-model/v2 bound to Registry v0.5.
- content-fields.yaml: bound Registry snapshot.
- manifest.json: file hashes and lineage.

This package contains no school template and no E2E expected output.
"""


def school_readme(school_id: str, status: str) -> str:
    return f"""# {school_id} school template base package

Purpose: final-generation school template input.

Files:
- final-template.docx: fillable candidate template.
- fill-contract.yaml: docfit-template-fill-contract/v2.
- content-fields.yaml: bound Registry snapshot.
- manifest.json: file hashes and contract counts.

Important: fill-contract.yaml status is {status}. This is a candidate template
package for base-package and placement validation. Do not report it as accepted.
"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise CheckFailure(f"source file missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def registry_identity(registry_path: Path, registry: dict[str, Any]) -> dict[str, str]:
    return {
        "registry_id": str(registry["registry_id"]),
        "registry_version": str(registry["registry_version"]),
        "sha256": sha256_file(registry_path),
    }


def file_meta(path: Path) -> dict[str, Any]:
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def make_writable(root: Path) -> None:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        current_path.chmod(0o700)
        for name in dirs:
            (current_path / name).chmod(0o700)
        for name in files:
            (current_path / name).chmod(0o600)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckFailure, ToolFailure) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
