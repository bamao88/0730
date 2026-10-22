"""DOCX package helpers for candidate package preparation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def managed_content_controls(template_path: Path) -> dict[str, str]:
    with ZipFile(template_path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))

    controls: dict[str, str] = {}
    for sdt in root.iter(f"{W}sdt"):
        properties = sdt.find(f"{W}sdtPr")
        if properties is None:
            continue
        tag = properties.find(f"{W}tag")
        alias = properties.find(f"{W}alias")
        if tag is None:
            continue
        tag_value = tag.get(f"{W}val")
        alias_value = alias.get(f"{W}val") if alias is not None else None
        if not tag_value or not alias_value:
            raise ValueError(f"managed content control lacks tag/alias: {template_path}")
        if tag_value in controls:
            raise ValueError(f"duplicate content-control tag {tag_value}: {template_path}")
        controls[tag_value] = alias_value
    return controls


def declared_content_control_fields(contract: dict[str, object]) -> dict[str, str]:
    declared: dict[str, str] = {}

    def add(locator: object, field_id: str) -> None:
        if not isinstance(locator, dict) or locator.get("type") != "content_control_tag":
            return
        tag = locator.get("value")
        if not isinstance(tag, str):
            raise ValueError(f"content-control locator lacks tag for {field_id}")
        previous = declared.get(tag)
        if previous is not None and previous != field_id:
            raise ValueError(f"tag {tag} maps to both {previous} and {field_id}")
        declared[tag] = field_id

    slots = contract.get("slots", [])
    if isinstance(slots, list):
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            field_id = str(slot["field_id"])
            add(slot.get("locator"), field_id)
            components = slot.get("component_locators", [])
            if isinstance(components, list):
                for component in components:
                    if isinstance(component, dict):
                        add(component.get("locator", component), field_id)
    regions = contract.get("regions", [])
    if isinstance(regions, list):
        for region in regions:
            if not isinstance(region, dict) or region.get("owner") != "slot":
                continue
            field_ids = region.get("field_ids", [])
            locators = [region.get("start_locator"), region.get("end_locator")]
            if not any(
                isinstance(locator, dict)
                and locator.get("type") == "content_control_tag"
                for locator in locators
            ):
                continue
            if not isinstance(field_ids, list) or len(field_ids) != 1:
                raise ValueError(
                    "content-control marker validation requires one field per "
                    f"slot region: {region.get('region_id')}"
                )
            add(region.get("start_locator"), str(field_ids[0]))
            add(region.get("end_locator"), str(field_ids[0]))
    return declared
