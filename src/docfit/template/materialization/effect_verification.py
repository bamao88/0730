"""Verify accepted effects against source objects and the reopened candidate."""

from __future__ import annotations

import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.template.materialization.text_edits import TextEdits, effect_failure
from docfit.tools.runtime import JsonObject
from docfit.tools.word_xml import W_NS, visible_word_text

W = f"{{{W_NS}}}"


class EffectVerification:
    def __init__(
        self,
        roots: list[ET.Element],
        *,
        mutable: set[ET.Element],
        removed: set[ET.Element],
        required_edits: set[str],
        wrapped: set[ET.Element] | None = None,
    ) -> None:
        self.roots = roots
        self.required_edits = required_edits
        self.removed = removed
        parents = {child: parent for root in roots for parent in root.iter() for child in parent}
        deleted_nodes = {node for root in removed for node in root.iter()}
        self.own = [
            (node, node.tag, dict(node.attrib), node.text, node.tail)
            for root in roots
            for node in root.iter()
            if node not in deleted_nodes
            and (node not in mutable or node.tag in {W + "p", W + "r", W + "pPr", W + "sdt"})
        ]
        excluded = set(mutable) | deleted_nodes
        # Wrapping a whole accepted table changes its ancestors, not the table
        # subtree itself. Keep that subtree protected, including its properties.
        for node in excluded | (wrapped or set()):
            while node in parents:
                node = parents[node]
                excluded.add(node)
        self.protected: list[tuple[ET.Element, bytes]] = []

        def collect(node: ET.Element) -> None:
            if node in deleted_nodes:
                return
            if node not in excluded:
                self.protected.append((node, ET.tostring(node)))
            else:
                for child in node:
                    collect(child)

        for root in roots:
            collect(root)
        protected_nodes = {node for node, _ in self.protected}
        self.order = [[node for node in root.iter() if node in protected_nodes] for root in roots]

    def verify(self, editor: TextEdits, expected_slots: set[str]) -> None:
        editor.verify_inline_positions()
        attached = {node for root in self.roots for node in root.iter()}
        if any(node in attached for node in self.removed):
            raise effect_failure("An accepted object deletion was not executed.")
        if not self.required_edits.issubset(editor.requests):
            raise effect_failure("An accepted text edit was not executed.")
        for node, original in self.protected:
            if node not in attached or ET.tostring(node) != original:
                raise effect_failure("A protected source object changed or disappeared.")
        for node, tag, attributes, text, tail in self.own:
            if node not in attached or (node.tag, node.attrib, node.text, node.tail) != (
                tag,
                attributes,
                text,
                tail,
            ):
                raise effect_failure("An unauthorized source property changed.")
        for root, order in zip(self.roots, self.order, strict=True):
            selected = set(order)
            if [node for node in root.iter() if node in selected] != order:
                raise effect_failure("Protected source objects changed their relative order.")
        for paragraph, expected in editor.expected_results().items():
            if paragraph not in attached or visible_word_text(paragraph) != expected:
                raise effect_failure("Actual text does not match the accepted source-span edits.")
        controls = Counter(
            node.get(W + "val") for root in self.roots for node in root.iter(W + "tag")
        )
        if any(controls[slot] != 1 for slot in expected_slots):
            raise effect_failure(
                "An accepted slot is absent or duplicated in the actual Word tree."
            )
        for ref, children in editor.requests.items():
            paragraph = editor.bound[ref].paragraph
            descendants = set(paragraph.iter())
            if any(child not in descendants for child in children):
                raise effect_failure("An inserted slot left its accepted source paragraph.")


def verify_written_package(
    candidate: Path,
    *,
    source: Path,
    changed_roots: dict[str, ET.Element],
) -> None:
    """Check reopened ZIP bytes/trees, independently of the writer's supplied payload."""
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        if before.namelist() != after.namelist():
            raise effect_failure("The candidate package changed its part inventory.")
        for name in before.namelist():
            if name in changed_roots:
                try:
                    actual = ET.fromstring(after.read(name))
                except ET.ParseError as error:
                    raise effect_failure(
                        "The candidate Word part could not be reopened."
                    ) from error
                if ET.tostring(actual) != ET.tostring(changed_roots[name]):
                    raise effect_failure("The reopened Word part differs from verified effects.")
            elif before.read(name) != after.read(name):
                raise effect_failure("An unselected package part changed.")


def has_verified_effects(receipt: JsonObject, candidate_hash: str | None = None) -> bool:
    proof = receipt.get("effect_verification")
    write = receipt.get("write")
    return bool(
        isinstance(proof, dict)
        and isinstance(write, dict)
        and all(
            isinstance(proof.get(key), str)
            and len(proof[key]) == 64
            and all(char in "0123456789abcdef" for char in proof[key])
            for key in ("source_sha256", "semantic_judgments_sha256", "candidate_sha256")
        )
        and proof.get("schema_version") == 3
        and proof.get("status") == "ok"
        and proof.get("reopened_package") is True
        and proof.get("source_sha256") == receipt.get("document_sha256")
        and proof.get("semantic_judgments_sha256") == receipt.get("semantic_judgments_sha256")
        and isinstance(proof.get("candidate_sha256"), str)
        and proof["candidate_sha256"] == write.get("output_sha256")
        and (candidate_hash is None or proof["candidate_sha256"] == candidate_hash)
    )
