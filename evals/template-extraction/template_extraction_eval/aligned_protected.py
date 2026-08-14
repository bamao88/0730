"""Exhaustive Gold-referenced protected-surface comparison.

The clean template is the truth for the current Eval stage.  Every protected
semantic fact emitted for Gold produces exactly one assertion.  Paragraphs are
aligned monotonically by content and container evidence, so deletions before a
paragraph do not turn every later paragraph index into a false mismatch.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .facts.effective_style import style_differences
from .markers import managed_marker_tags
from .models import (
    AssertionResult,
    AssertionStatus,
    DocumentFacts,
    EffectiveStyle,
    EvalConfig,
    FillContract,
    Owner,
    ParagraphFact,
    ResponsibilityAtom,
    ResponsibilityInventory,
    RunFact,
    View,
    stable_data,
)
from .responsibility import build_responsibility_inventory

SLOT_TOKEN = "<SLOT>"


@dataclass(frozen=True)
class ParagraphProjection:
    paragraph: ParagraphFact
    masked_text: str
    slot_intervals: tuple[tuple[int, int], ...]
    block_slot: bool


@dataclass(frozen=True)
class ParagraphAlignment:
    gold: ParagraphProjection
    actual: ParagraphProjection | None
    similarity: float
    method: str


@dataclass(frozen=True)
class AlignedProtectedAudit:
    gold_inventory: ResponsibilityInventory
    actual_inventory: ResponsibilityInventory
    assertions: tuple[AssertionResult, ...]
    alignments: tuple[ParagraphAlignment, ...]

    @property
    def expected_atoms(self) -> int:
        return self.gold_inventory.protected

    @property
    def asserted_atoms(self) -> int:
        return len(self.assertions)

    @property
    def responsibility_coverage(self) -> float:
        if self.expected_atoms == 0:
            return 0.0
        return self.asserted_atoms / self.expected_atoms


def _key(paragraph: ParagraphFact) -> tuple[str, str, int]:
    return paragraph.story, paragraph.part, paragraph.paragraph_index


def _merge_intervals(values: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(values):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return tuple(merged)


def _mask(text: str, intervals: tuple[tuple[int, int], ...]) -> str:
    if not intervals:
        return text
    result: list[str] = []
    cursor = 0
    for start, end in intervals:
        bounded_start = max(cursor, min(len(text), start))
        bounded_end = max(bounded_start, min(len(text), end))
        result.append(text[cursor:bounded_start])
        result.append(SLOT_TOKEN)
        cursor = bounded_end
    result.append(text[cursor:])
    return "".join(result)


def _projections(
    facts: DocumentFacts,
    contract: FillContract,
) -> tuple[ParagraphProjection, ...]:
    tags = managed_marker_tags(contract)
    block_keys: set[tuple[str, str, int]] = set()
    inline: dict[tuple[str, str, int], list[tuple[int, int]]] = defaultdict(list)
    for control in facts.controls:
        if control.tag not in tags:
            continue
        if control.block_level:
            indices = control.paragraph_indices or (control.paragraph_index,)
            block_keys.update(
                (control.story, control.part, index) for index in indices
            )
        else:
            inline[(control.story, control.part, control.paragraph_index)].append(
                (control.start, control.end)
            )
    result: list[ParagraphProjection] = []
    for paragraph in facts.paragraphs:
        paragraph_key = _key(paragraph)
        intervals = _merge_intervals(inline.get(paragraph_key, []))
        block_slot = paragraph_key in block_keys
        result.append(
            ParagraphProjection(
                paragraph=paragraph,
                masked_text=SLOT_TOKEN if block_slot else _mask(paragraph.text, intervals),
                slot_intervals=intervals,
                block_slot=block_slot,
            )
        )
    return tuple(result)


def _match_normalize(value: str) -> str:
    value = value.replace("：", ":")
    return re.sub(r"[\s□]", "", value)


def _ordered_fragments(text: str) -> tuple[str, ...]:
    return tuple(fragment for fragment in text.split(SLOT_TOKEN) if fragment)


def _contains_in_order(haystack: str, fragments: tuple[str, ...]) -> bool:
    cursor = 0
    for fragment in fragments:
        position = haystack.find(fragment, cursor)
        if position < 0:
            return False
        cursor = position + len(fragment)
    return True


def _paragraph_similarity(
    gold: ParagraphProjection,
    actual: ParagraphProjection,
) -> tuple[float, str]:
    gold_paragraph = gold.paragraph
    actual_paragraph = actual.paragraph
    if (gold_paragraph.story, gold_paragraph.part) != (
        actual_paragraph.story,
        actual_paragraph.part,
    ):
        return 0.0, "different_story"
    gold_text = gold.masked_text
    actual_text = actual.masked_text
    if (
        not gold_text
        and not actual_text
        and (gold_paragraph.table_index is None)
        != (actual_paragraph.table_index is None)
    ):
        return 0.0, "empty_container_mismatch"
    if gold_text == actual_text and gold_text:
        return 1.0, "exact_text"
    if not gold_text and not actual_text:
        return 0.62, "empty_context"
    normalized_gold = _match_normalize(gold_text)
    normalized_actual = _match_normalize(actual_text)
    if normalized_gold == normalized_actual and normalized_gold:
        return 0.96, "normalized_text"
    if (
        len(normalized_gold.replace(SLOT_TOKEN, "")) >= 4
        and normalized_gold.replace(SLOT_TOKEN, "") in normalized_actual
    ):
        return 0.86, "gold_text_contained"
    fragments = tuple(
        _match_normalize(item) for item in _ordered_fragments(gold_text)
        if _match_normalize(item)
    )
    if SLOT_TOKEN in gold_text and fragments and _contains_in_order(
        normalized_actual,
        fragments,
    ):
        return 0.88, "protected_fragments"
    same_cell = (
        gold_paragraph.table_index is not None
        and actual_paragraph.table_index is not None
        and gold_paragraph.row == actual_paragraph.row
        and gold_paragraph.cell == actual_paragraph.cell
    )
    if normalized_gold and normalized_actual:
        ratio = SequenceMatcher(
            None,
            normalized_gold.replace(SLOT_TOKEN, ""),
            normalized_actual.replace(SLOT_TOKEN, ""),
            autojunk=False,
        ).ratio()
        if same_cell and ratio >= 0.2:
            return max(0.72, ratio * 0.9), "table_cell_and_text"
        if ratio >= 0.58:
            return ratio * 0.9, "fuzzy_text"
    if same_cell:
        return 0.68, "table_cell"
    if gold_text == SLOT_TOKEN:
        return 0.48, "slot_only_context"
    return 0.0, "no_evidence"


def _align_group(
    gold: tuple[ParagraphProjection, ...],
    actual: tuple[ParagraphProjection, ...],
) -> tuple[ParagraphAlignment, ...]:
    """Monotonic dynamic alignment; every Gold paragraph receives an outcome."""

    gold_count = len(gold)
    actual_count = len(actual)
    negative = float("-inf")
    scores = [[negative] * (actual_count + 1) for _ in range(gold_count + 1)]
    decisions = [[""] * (actual_count + 1) for _ in range(gold_count + 1)]
    scores[0][0] = 0.0
    for actual_index in range(1, actual_count + 1):
        scores[0][actual_index] = scores[0][actual_index - 1]
        decisions[0][actual_index] = "skip_actual"
    for gold_index in range(1, gold_count + 1):
        scores[gold_index][0] = scores[gold_index - 1][0] - 1.0
        decisions[gold_index][0] = "skip_gold"

    similarity_cache: dict[tuple[int, int], tuple[float, str]] = {}
    for gold_index in range(1, gold_count + 1):
        for actual_index in range(1, actual_count + 1):
            similarity, method = _paragraph_similarity(
                gold[gold_index - 1],
                actual[actual_index - 1],
            )
            similarity_cache[(gold_index, actual_index)] = (similarity, method)
            candidates = [
                (scores[gold_index][actual_index - 1], 1, "skip_actual"),
                (scores[gold_index - 1][actual_index] - 1.0, 0, "skip_gold"),
            ]
            if similarity >= 0.45:
                candidates.append(
                    (
                        scores[gold_index - 1][actual_index - 1]
                        + 1.0
                        + similarity * 2.0,
                        2,
                        "match",
                    )
                )
            best = max(candidates, key=lambda item: (item[0], item[1]))
            scores[gold_index][actual_index] = best[0]
            decisions[gold_index][actual_index] = best[2]

    aligned: dict[int, ParagraphAlignment] = {}
    gold_index = gold_count
    actual_index = actual_count
    while gold_index or actual_index:
        decision = decisions[gold_index][actual_index]
        if decision == "match":
            similarity, method = similarity_cache[(gold_index, actual_index)]
            aligned[gold_index - 1] = ParagraphAlignment(
                gold=gold[gold_index - 1],
                actual=actual[actual_index - 1],
                similarity=similarity,
                method=method,
            )
            gold_index -= 1
            actual_index -= 1
        elif decision == "skip_actual":
            actual_index -= 1
        else:
            aligned[gold_index - 1] = ParagraphAlignment(
                gold=gold[gold_index - 1],
                actual=None,
                similarity=0.0,
                method="missing",
            )
            gold_index -= 1
    return tuple(aligned[index] for index in range(gold_count))


def align_paragraphs(
    gold_facts: DocumentFacts,
    actual_facts: DocumentFacts,
    gold_contract: FillContract,
    actual_contract: FillContract,
) -> tuple[ParagraphAlignment, ...]:
    gold_groups: dict[tuple[str, str], list[ParagraphProjection]] = defaultdict(list)
    actual_groups: dict[tuple[str, str], list[ParagraphProjection]] = defaultdict(list)
    for projection in _projections(gold_facts, gold_contract):
        paragraph = projection.paragraph
        gold_groups[(paragraph.story, paragraph.part)].append(projection)
    for projection in _projections(actual_facts, actual_contract):
        paragraph = projection.paragraph
        actual_groups[(paragraph.story, paragraph.part)].append(projection)
    results: list[ParagraphAlignment] = []
    for group in sorted(gold_groups):
        results.extend(
            _align_group(
                tuple(gold_groups[group]),
                tuple(actual_groups.get(group, [])),
            )
        )
    return tuple(results)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _failure_code(dimension: str, status: AssertionStatus) -> str | None:
    if status is not AssertionStatus.FAIL:
        return None
    if dimension == "protected.content":
        return "required_protected_content_missing_or_changed"
    if dimension == "protected.object":
        return "required_protected_object_missing_or_broken"
    return None


def _assertion(
    atom: ResponsibilityAtom,
    status: AssertionStatus,
    actual: Any,
    message: str,
) -> AssertionResult:
    return AssertionResult(
        assertion_id=f"protected.aligned.{_digest(atom.atom_id)}",
        view=View.PROTECTED,
        dimension=atom.dimension,
        status=status,
        required=True,
        expected=stable_data(atom.value),
        actual=stable_data(actual),
        message=f"{atom.locator}: {message}",
        failure_code=_failure_code(atom.dimension, status),
    )


def _paragraph_path_from_atom(atom: ResponsibilityAtom) -> str | None:
    if not atom.atom_id.startswith("paragraph:"):
        return None
    suffixes = (":content", ":structure")
    for suffix in suffixes:
        if atom.atom_id.endswith(suffix):
            return atom.atom_id[len("paragraph:") : -len(suffix)]
    match = re.match(r"^paragraph:(.*):protected-run\[(\d+)\](?:#\d+)?$", atom.atom_id)
    return None if match is None else match.group(1)


def _protected_runs(
    projection: ParagraphProjection,
) -> tuple[RunFact, ...]:
    if projection.block_slot:
        return ()
    result: list[RunFact] = []
    for run in projection.paragraph.runs:
        overlaps = any(
            (run.start < end and run.end > start)
            or (run.start == run.end and start <= run.start < end)
            for start, end in projection.slot_intervals
        )
        if not overlaps:
            result.append(run)
    return tuple(result)


def _run_index(atom: ResponsibilityAtom) -> int | None:
    match = re.search(r":protected-run\[(\d+)\](?:#\d+)?$", atom.atom_id)
    return None if match is None else int(match.group(1))


def _style_at(paragraph: ParagraphFact, position: int) -> EffectiveStyle | None:
    for run in paragraph.runs:
        if run.start <= position < run.end:
            return run.effective_style
    for run in paragraph.runs:
        if run.start == run.end == position:
            return run.effective_style
    if position == len(paragraph.text) and paragraph.runs:
        return paragraph.runs[-1].effective_style
    return None


def _observed_style(
    atom: ResponsibilityAtom,
    gold_projection: ParagraphProjection,
    actual_projection: ParagraphProjection,
) -> EffectiveStyle | None:
    index = _run_index(atom)
    if index is None:
        return None
    gold_runs = _protected_runs(gold_projection)
    if index >= len(gold_runs):
        return None
    actual_runs = _protected_runs(actual_projection)
    if (
        gold_projection.paragraph.text == actual_projection.paragraph.text
        and len(gold_runs) == len(actual_runs)
    ):
        return actual_runs[index].effective_style
    gold_run = gold_runs[index]
    if not gold_run.text:
        return _style_at(actual_projection.paragraph, 0)
    if gold_projection.paragraph.text == actual_projection.paragraph.text:
        return _style_at(actual_projection.paragraph, gold_run.start)
    position = actual_projection.paragraph.text.find(gold_run.text)
    if position >= 0:
        return _style_at(actual_projection.paragraph, position)
    if gold_projection.masked_text == actual_projection.masked_text and gold_run.start <= len(
        actual_projection.paragraph.text
    ):
        return _style_at(actual_projection.paragraph, gold_run.start)
    return None


def _normalized_structure(value: Any) -> Any:
    data = stable_data(value)
    if not isinstance(data, dict):
        return data
    result = dict(data)
    # Absolute indices shift when instructions/examples are removed.  Logical
    # story and container coordinates remain meaningful comparison facts.
    for key in ("paragraph_index", "section_index", "table_index"):
        result.pop(key, None)
    return result


def _paragraph_atom_result(
    atom: ResponsibilityAtom,
    alignment: ParagraphAlignment,
    config: EvalConfig,
) -> AssertionResult:
    actual_projection = alignment.actual
    if actual_projection is None:
        return _assertion(atom, AssertionStatus.FAIL, None, "required Gold paragraph is missing")
    if atom.dimension == "protected.content":
        expected = str(atom.value)
        actual = actual_projection.masked_text
        if SLOT_TOKEN in expected:
            fragments = _ordered_fragments(expected)
            matches = bool(fragments) and _contains_in_order(actual, fragments)
        else:
            matches = expected == actual
        return _assertion(
            atom,
            AssertionStatus.PASS if matches else AssertionStatus.FAIL,
            actual,
            f"protected text {'matches' if matches else 'differs'}; alignment={alignment.method}",
        )
    if atom.dimension == "protected.structure":
        actual_value = {
            "story": actual_projection.paragraph.story,
            "part": actual_projection.paragraph.part,
            "paragraph_index": actual_projection.paragraph.paragraph_index,
            "section_index": actual_projection.paragraph.section_index,
            "table_index": actual_projection.paragraph.table_index,
            "row": actual_projection.paragraph.row,
            "cell": actual_projection.paragraph.cell,
        }
        matches = _normalized_structure(atom.value) == _normalized_structure(actual_value)
        return _assertion(
            atom,
            AssertionStatus.PASS if matches else AssertionStatus.FAIL,
            actual_value,
            (
                f"logical structure {'matches' if matches else 'differs'}; "
                f"alignment={alignment.method}"
            ),
        )
    if atom.dimension == "protected.style":
        actual_style = _observed_style(atom, alignment.gold, actual_projection)
        if actual_style is None or not isinstance(atom.value, EffectiveStyle):
            return _assertion(
                atom,
                AssertionStatus.UNKNOWN,
                actual_style,
                f"style position cannot be aligned; alignment={alignment.method}",
            )
        differences = style_differences(atom.value, actual_style, config.tolerances)
        return _assertion(
            atom,
            AssertionStatus.FAIL if differences else AssertionStatus.PASS,
            actual_style,
            (
                f"effective style differs: {differences}; alignment={alignment.method}"
                if differences
                else f"effective style matches; alignment={alignment.method}"
            ),
        )
    raise AssertionError(f"unexpected paragraph atom dimension: {atom.dimension}")


def _table_mapping(
    alignments: tuple[ParagraphAlignment, ...],
) -> dict[tuple[str, str, int], tuple[str, str, int]]:
    candidates: dict[tuple[str, str, int], list[tuple[str, str, int]]] = defaultdict(list)
    for alignment in alignments:
        gold_paragraph = alignment.gold.paragraph
        actual = alignment.actual
        if (
            gold_paragraph.table_index is None
            or actual is None
            or actual.paragraph.table_index is None
        ):
            continue
        candidates[
            (gold_paragraph.story, gold_paragraph.part, gold_paragraph.table_index)
        ].append(
            (
                actual.paragraph.story,
                actual.paragraph.part,
                actual.paragraph.table_index,
            )
        )
    result: dict[tuple[str, str, int], tuple[str, str, int]] = {}
    for key, values in candidates.items():
        result[key] = Counter(values).most_common(1)[0][0]
    return result


def _parse_table_atom(atom: ResponsibilityAtom) -> tuple[str, str, int] | None:
    match = re.match(r"^table:(.*):([^:]+):table\[(\d+)\]$", atom.atom_id)
    if match is None:
        return None
    return match.group(2), match.group(1), int(match.group(3))


def _actual_atom_for_table(
    atom: ResponsibilityAtom,
    table_map: dict[tuple[str, str, int], tuple[str, str, int]],
    actual_atoms: tuple[ResponsibilityAtom, ...],
) -> ResponsibilityAtom | None:
    gold_key = _parse_table_atom(atom)
    if gold_key is None:
        return None
    actual_key = table_map.get(gold_key)
    if actual_key is None:
        return None
    story, part, table_index = actual_key
    expected_id = f"table:{part}:{story}:table[{table_index}]"
    return next((item for item in actual_atoms if item.atom_id == expected_id), None)


def _object_paragraph_prefix(paragraph: ParagraphFact) -> str:
    return f"{paragraph.part}:{paragraph.story}:p[{paragraph.paragraph_index}]/"


def _semantic_atom_match(
    expected: ResponsibilityAtom,
    candidates: tuple[ResponsibilityAtom, ...],
) -> ResponsibilityAtom | None:
    expected_value = _comparable_atom_value(expected)
    return next(
        (
            item
            for item in candidates
            if item.dimension == expected.dimension
            and _comparable_atom_value(item) == expected_value
        ),
        None,
    )


def _comparable_atom_value(atom: ResponsibilityAtom) -> Any:
    value = stable_data(atom.value)
    if atom.dimension != "protected.object" or not isinstance(value, dict):
        return value
    result = dict(value)
    for key in ("paragraph_index", "relationship_id", "detail"):
        result.pop(key, None)
    if result.get("kind") == "bookmark":
        # OOXML bookmark numeric ids are package-local implementation details;
        # bookmark names carry the cross-document identity.
        result.pop("value", None)
        result.pop("semantic_xml", None)
    return result


def evaluate_aligned_exhaustive_protected(
    gold_facts: DocumentFacts,
    actual_facts: DocumentFacts,
    gold_contract: FillContract,
    actual_contract: FillContract,
    config: EvalConfig,
) -> AlignedProtectedAudit:
    """Emit one result for every Gold protected atom, with no sampling."""

    gold_inventory = build_responsibility_inventory(gold_facts, gold_contract)
    actual_inventory = build_responsibility_inventory(actual_facts, actual_contract)
    alignments = align_paragraphs(
        gold_facts,
        actual_facts,
        gold_contract,
        actual_contract,
    )
    alignment_by_path = {
        item.gold.paragraph.path: item
        for item in alignments
    }
    actual_atoms = tuple(
        atom for atom in actual_inventory.atoms if atom.owner is Owner.PROTECTED
    )
    consumed_actual_atom_ids: set[str] = set()
    table_map = _table_mapping(alignments)
    assertions: list[AssertionResult] = []

    for atom in gold_inventory.atoms:
        if atom.owner is not Owner.PROTECTED:
            continue
        paragraph_path = _paragraph_path_from_atom(atom)
        if paragraph_path is not None:
            alignment = alignment_by_path.get(paragraph_path)
            if alignment is None:
                assertions.append(
                    _assertion(atom, AssertionStatus.FAIL, None, "Gold paragraph was not analyzed")
                )
            else:
                assertions.append(_paragraph_atom_result(atom, alignment, config))
            continue
        object_semantics_uncertain = False
        if atom.atom_id.startswith("table:"):
            observed = _actual_atom_for_table(atom, table_map, actual_atoms)
        elif atom.atom_id.startswith("object:"):
            gold_paragraph = next(
                (
                    item.gold.paragraph
                    for item in alignments
                    if atom.locator.startswith(_object_paragraph_prefix(item.gold.paragraph))
                ),
                None,
            )
            alignment = None if gold_paragraph is None else alignment_by_path[gold_paragraph.path]
            if "p[None]/" in atom.locator:
                observed = _semantic_atom_match(
                    atom,
                    tuple(
                        item
                        for item in actual_atoms
                        if item.atom_id not in consumed_actual_atom_ids
                    ),
                )
            elif alignment is None or alignment.actual is None:
                observed = None
            else:
                prefix = _object_paragraph_prefix(alignment.actual.paragraph)
                observed = _semantic_atom_match(
                    atom,
                    tuple(
                        item
                        for item in actual_atoms
                        if item.atom_id not in consumed_actual_atom_ids
                        and item.locator.startswith(prefix)
                    ),
                )
            atom_value = stable_data(atom.value)
            if (
                observed is None
                and isinstance(atom_value, dict)
                and atom_value.get("kind") == "bookmark"
            ):
                observed = next(
                    (
                        item
                        for item in actual_atoms
                        if item.atom_id not in consumed_actual_atom_ids
                        and item.dimension == "protected.object"
                        and isinstance(stable_data(item.value), dict)
                        and stable_data(item.value).get("kind") == "bookmark"
                        and stable_data(item.value).get("part") == atom_value.get("part")
                        and stable_data(item.value).get("story") == atom_value.get("story")
                    ),
                    None,
                )
                object_semantics_uncertain = observed is not None
        elif atom.atom_id.startswith("part:"):
            observed = next(
                (item for item in actual_atoms if item.atom_id == atom.atom_id),
                None,
            )
        else:
            observed = _semantic_atom_match(
                atom,
                tuple(
                    item
                    for item in actual_atoms
                    if item.atom_id not in consumed_actual_atom_ids
                ),
            )

        if observed is not None and atom.atom_id.startswith(
            ("object:", "relationship:", "protected-control:")
        ):
            consumed_actual_atom_ids.add(observed.atom_id)

        if observed is None:
            assertions.append(
                _assertion(atom, AssertionStatus.FAIL, None, "required protected fact is missing")
            )
        elif object_semantics_uncertain:
            assertions.append(
                _assertion(
                    atom,
                    AssertionStatus.UNKNOWN,
                    observed.value,
                    "bookmark exists, but cross-document target semantics cannot be proven",
                )
            )
        elif not atom.analyzable or not observed.analyzable:
            assertions.append(
                _assertion(
                    atom,
                    AssertionStatus.UNKNOWN,
                    observed.value,
                    "protected fact is present but its semantics are unsupported",
                )
            )
        else:
            matches = _comparable_atom_value(atom) == _comparable_atom_value(observed)
            assertions.append(
                _assertion(
                    atom,
                    AssertionStatus.PASS if matches else AssertionStatus.FAIL,
                    observed.value,
                    "protected fact matches" if matches else "protected fact differs",
                )
            )

    if len(assertions) != gold_inventory.protected:
        raise AssertionError(
            "exhaustive protected evaluator did not emit exactly one assertion per Gold atom"
        )
    return AlignedProtectedAudit(
        gold_inventory=gold_inventory,
        actual_inventory=actual_inventory,
        assertions=tuple(assertions),
        alignments=alignments,
    )


def aligned_audit_summary(audit: AlignedProtectedAudit) -> dict[str, Any]:
    statuses = Counter(item.status.value for item in audit.assertions)
    methods = Counter(item.method for item in audit.alignments)
    return {
        "expected_gold_protected_atoms": audit.expected_atoms,
        "asserted_gold_protected_atoms": audit.asserted_atoms,
        "responsibility_coverage": audit.responsibility_coverage,
        "assertion_statuses": dict(sorted(statuses.items())),
        "paragraph_alignment_methods": dict(sorted(methods.items())),
        "matched_paragraphs": sum(item.actual is not None for item in audit.alignments),
        "missing_gold_paragraphs": sum(item.actual is None for item in audit.alignments),
    }


__all__ = [
    "AlignedProtectedAudit",
    "ParagraphAlignment",
    "align_paragraphs",
    "aligned_audit_summary",
    "evaluate_aligned_exhaustive_protected",
]
