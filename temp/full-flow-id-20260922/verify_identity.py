"""Independent fresh-run identity audit, replay, and unopened-range checks."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import yaml

from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import validate_published_template_artifact
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.object_mutation import resolve_word_locator
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_entries import CanonicalSourceInventory
from docfit.template.unit_source import (
    load_initial_inventory, require_initial_binding, validate_unit_proof,
)
from docfit.tools.runtime import sha256_file, sha256_json

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
PARA_ID = '{http://schemas.microsoft.com/office/word/2010/wordml}paraId'

def read(path):
    return json.loads(path.read_text())

def tree(path):
    with ZipFile(path) as archive:
        return ET.fromstring(archive.read('word/document.xml'))

def shape(element):
    return (element.tag, sorted(element.attrib.items()), element.text or '',
            [shape(child) for child in element])

def text(element):
    return ''.join(node.text or '' for node in element.iter(W+'t'))

def audit(root: Path, output: Path):
    source = root / 'input/school-template.docx'
    initial = load_initial_inventory(root, sha256_file(source))
    canonical = CanonicalSourceInventory.from_json(initial['canonical_source_inventory'])
    proof = read(root / 'work/.docfit/unit-boundary-checkpoint.json')
    units = validate_unit_proof(canonical, proof)
    inventory = read(root / 'work/.docfit/harness/object-inventory.json')
    require_initial_binding(root, inventory)
    review = read(root / 'work/.docfit/harness/semantic-judgments.json')
    assert review_uses_current_semantic_shape(review=review, inventory=inventory, expected_vocabulary=inventory["field_id_vocabulary"])
    spans = review['resolved_spans']
    entry_ids = {entry.source_entry_id for entry in canonical.source_entries}
    assert {span['source_entry_id'] for span in spans} == entry_ids
    final = root / 'output/final-template.docx'
    contract = yaml.safe_load((root / 'output/fill-contract.yaml').read_text())
    artifact = validate_published_template_artifact(template_docx=final, fill_contract=contract)
    registry = FieldRegistrySnapshot.load(root / 'input/field-registry.yaml')
    replay_dir = output.parent / (root.name + '-replay')
    replay_dir.mkdir(parents=True, exist_ok=True)
    replay_doc = replay_dir / 'candidate.docx'
    materialization = materialize_template_from_semantics(
        source_docx=source, output_docx=replay_doc, registry=registry,
        inventory=inventory, review=review,
    )
    (replay_dir / 'materialization.json').write_text(json.dumps(materialization, ensure_ascii=False, indent=2)+'\n')
    assert shape(tree(replay_doc)) == shape(tree(final)), 'Replay Word content differs from published Word'
    source_tree, final_tree = tree(source), tree(final)
    parents = {id(child): parent for parent in source_tree.iter() for child in parent}
    affected: set[str] = set()
    mutation_roles = {'fill_slot','body_structure','cleanup','generated_content','style_only'}
    for span in spans:
        if span.get('role') not in mutation_roles:
            continue
        for fragment in span['word_fragments']:
            element = resolve_word_locator(source_tree, fragment['locator'])
            assert element is not None
            if element.tag == W+'p':
                if element.get(PARA_ID): affected.add(element.get(PARA_ID))
            for paragraph in element.iter(W+'p'):
                if paragraph.get(PARA_ID): affected.add(paragraph.get(PARA_ID))
            parent = parents.get(id(element))
            while parent is not None and parent.tag != W+'body':
                if parent.tag == W+'p' and parent.get(PARA_ID): affected.add(parent.get(PARA_ID))
                parent = parents.get(id(parent))
    originals = [p for p in source_tree.iter(W+'p') if p.get(PARA_ID) not in affected]
    final_by_id = {}
    for p in final_tree.iter(W+'p'):
        if p.get(PARA_ID): final_by_id.setdefault(p.get(PARA_ID), []).append(p)
    checked = []
    for paragraph in originals:
        pid = paragraph.get(PARA_ID)
        if not pid: continue
        matches = final_by_id.get(pid, [])
        assert len(matches) == 1, ('untouched paragraph missing or duplicated', pid)
        assert shape(matches[0]) == shape(paragraph), ('untouched paragraph changed', pid, text(paragraph))
        checked.append(pid)
    with ZipFile(source) as left, ZipFile(final) as right:
        unchanged_parts=[]
        for name in left.namelist():
            if name.startswith(('word/header','word/footer','word/media/')):
                assert left.read(name) == right.read(name), ('untouched Word part changed', name)
                unchanged_parts.append(name)
    rejected=[]
    old=copy.deepcopy(proof); old['schema_version']=1
    corrupt=copy.deepcopy(proof)
    span=next(s for u in corrupt['resolved_units'] for s in u['source_spans'] if s['extent']['kind']=='text')
    span['extent']['start'] += 1
    corrupt['unit_projection_digest']=sha256_json(corrupt['resolved_units'])
    for name,value in [('old_proof',old),('changed_extent_rehashed',corrupt)]:
        try: validate_unit_proof(canonical,value)
        except ValueError: rejected.append(name)
        else: raise AssertionError(('corrupt proof accepted',name))
    result={
        'root':str(root), 'source_sha256':sha256_file(source),
        'initial_inventory_digest':canonical.inventory_digest,
        'unit_count':len(units),'source_entry_count':len(entry_ids),
        'span_count':len(spans),'slot_count':len(contract['slots']),
        'artifact_check':artifact, 'replay':'ok',
        'replay_output_sha256':sha256_file(replay_doc),
        'untouched_paragraph_ids':checked,'unchanged_header_footer_media_parts':unchanged_parts,
        'negative_rejections':rejected,
        'scope':'source identity and actual Word ranges; no school semantic or visual acceptance',
    }
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if not isinstance(v,(dict,list))}, ensure_ascii=False))

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();audit(args.root.resolve(),args.output)
