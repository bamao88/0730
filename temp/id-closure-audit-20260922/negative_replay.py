from pathlib import Path
from copy import deepcopy
import json
from docfit.fields import FieldRegistrySnapshot
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_spans import SourceSpan,TextSourceExtent,source_span_ref
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.artifact import validate_published_template_artifact
from docfit.content.placement import load_fill_contract
from docfit.tools.runtime import ToolFailure,sha256_file,sha256_json

root=Path('temp/phase8-v05-20260912/hunau-01-cover-v5')
output=Path('temp/id-closure-audit-20260922/negative-replay')
output.mkdir(exist_ok=True)
inventory=json.loads((root/'work/.docfit/harness/object-inventory.json').read_text())
accepted=json.loads((root/'work/.docfit/harness/semantic-judgments.json').read_text())
registry=FieldRegistrySnapshot.load(root/'input/field-registry.yaml')
vocabulary=registry.pre_input_vocabulary()
assert review_uses_current_semantic_shape(inventory=inventory,review=accepted,expected_vocabulary=vocabulary,expected_document_sha256=sha256_file(root/'input/school-template.docx'))
results=[]
for kind in ['unknown_field','retired_alias','independent_target','swapped_extents']:
 review=deepcopy(accepted)
 if kind=='swapped_extents':
  j=next(j for j in review['semantic_judgments'] if len([s for s in j['resolved_spans'] if s['extent']['kind']=='text'])>=2)
  a,b=[s for s in j['resolved_spans'] if s['extent']['kind']=='text'][:2]
  keys=['extent','text_start','text_end','word_fragments','expected_source_content']
  av,bv=deepcopy(a),deepcopy(b)
  for key in keys:
   if key in bv:a[key]=deepcopy(bv[key])
   if key in av:b[key]=deepcopy(av[key])
  for s in [a,b]:
   s['span_ref']=source_span_ref(source_snapshot_sha256=s['source_snapshot_sha256'],source_span=SourceSpan(s['source_entry_id'],TextSourceExtent(s['extent']['start'],s['extent']['end'])))
   if 'slot_ref' in s:s['slot_ref']=s['span_ref']+';field_id='+s['field_id']
 else:
  j=next(j for j in review['semantic_judgments'] if any('field_id' in p for p in j['parts']))
  part=next(p for p in j['parts'] if 'field_id' in p)
  if kind=='unknown_field':part['field_id']='audit.not.in.input.vocabulary'
  elif kind=='retired_alias':part['registry_field']=part.pop('field_id')
  elif kind=='independent_target':part['target_ref']={'locator':'/body/p[1]'}
 review['resolved_spans']=[s for j in review['semantic_judgments'] for s in j['resolved_spans']]
 review['semantic_judgments_sha256']=sha256_json(review['semantic_judgments'])
 assert not review_uses_current_semantic_shape(inventory=inventory,review=review,expected_vocabulary=vocabulary,expected_document_sha256=inventory['document_sha256'])
 out=output/(kind+'.docx')
 try:materialize_template_from_semantics(source_docx=root/'input/school-template.docx',output_docx=out,registry=registry,inventory=inventory,review=review)
 except ToolFailure as e:results.append({'case':kind,'rejected':True,'code':e.code,'output_absent':not out.exists()})
 else:raise AssertionError(kind+' accepted')
 assert not out.exists()
contract=load_fill_contract(root/'output/fill-contract.yaml')
validate_published_template_artifact(template_docx=root/'output/final-template.docx',fill_contract=contract)
for kind in ['legacy_contract','orphan_slot','different_word_file']:
 bad=deepcopy(contract);word=root/'output/final-template.docx'
 if kind=='legacy_contract':bad['schema_version']='docfit-template-fill-contract/v1'
 elif kind=='orphan_slot':bad['slots'][0]['field_id']='audit.not.in.input.vocabulary'
 else:word=root/'input/school-template.docx'
 try:validate_published_template_artifact(template_docx=word,fill_contract=bad)
 except ToolFailure as e:results.append({'case':kind,'rejected':True,'code':e.code})
 else:raise AssertionError(kind+' accepted')
Path('temp/id-closure-audit-20260922/negative-replay.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
