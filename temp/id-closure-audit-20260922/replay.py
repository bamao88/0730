from pathlib import Path
import json,zipfile
from xml.etree import ElementTree as ET
from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.artifact import publication_slot_protocol_status
from docfit.app.prepare_template import _accepted_review_allows_no_published_slots
from docfit.tools.runtime import ToolFailure,sha256_file

HERE=Path('temp/id-closure-audit-20260922')
rows=json.loads((HERE/'artifact-audit.json').read_text())['rows']
copies=json.loads((HERE/'source-copies.json').read_text())['found']
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
results=[]
for row in rows:
 root=Path(row['root']);name=root.name;h=root/'work/.docfit/harness'
 inv=json.loads((h/'object-inventory.json').read_text());review=json.loads((h/'semantic-judgments.json').read_text());reg=FieldRegistrySnapshot.load(root/'input/field-registry.yaml')
 src=root/'input/school-template.docx';out=HERE/'replay'/name/'candidate.docx'
 result={'root':str(root)}
 if not row['source_current']:
  try:materialize_template_from_semantics(source_docx=src,output_docx=out.parent/"rejected-stale.docx",registry=reg,inventory=inv,review=review)
  except ToolFailure as e:result['stale_source_rejection']=e.code
  else:raise AssertionError('stale source accepted')
  assert not (out.parent/"rejected-stale.docx").exists()
  options=copies.get(row['ledger_source_sha256'],[])
  if not options:
   result['replay']='source_snapshot_unavailable';results.append(result);print(name,result,flush=True);continue
  src=Path(options[0])
 assert sha256_file(src)==row['ledger_source_sha256']
 result['source_path']=str(src);result['source_sha256']=sha256_file(src)
 try:
  out.parent.mkdir(parents=True,exist_ok=True)
  mat=materialize_template_from_semantics(source_docx=src,output_docx=out,registry=reg,inventory=inv,review=review)
  (out.parent/'materialization.json').write_text(json.dumps(mat,ensure_ascii=False,indent=2)+'\n')
  protocol=publication_slot_protocol_status(candidate_docx=out,registry=reg,allow_no_slots=_accepted_review_allows_no_published_slots(review))
  assert protocol['status']=='ok',protocol
  spans={s['slot_ref']:s for s in review['resolved_spans'] if s.get('slot_ref')}
  with zipfile.ZipFile(out) as z:doc=ET.fromstring(z.read('word/document.xml'))
  controls=[]
  for sdt in doc.iter(W+'sdt'):
   tag=sdt.find(W+'sdtPr/'+W+'tag');alias=sdt.find(W+'sdtPr/'+W+'alias')
   if tag is None or not tag.get(W+'val','').startswith('source_entry_id='):continue
   ref=tag.get(W+'val');field=alias.get(W+'val') if alias is not None else None
   assert ref in spans and spans[ref]['field_id']==field,(ref,field)
   assert field in inv['field_id_vocabulary']['allowed_field_ids']
   controls.append({'slot_ref':ref,'field_id':field})
  assert len(controls)==protocol['slot_count'],(len(controls),protocol)
  assert {c['slot_ref'] for c in controls}=={s['slot_ref'] for s in __import__('yaml').safe_load((root/'output/fill-contract.yaml').read_text())['slots']}
  result.update(replay='ok',output_sha256=sha256_file(out),operation_count=mat['operation_count'],slot_count=len(controls),actual_controls=controls)
 except Exception as e:
  result.update(replay='failed',error_type=type(e).__name__,error=str(e),code=getattr(e,'code',None))
 results.append(result);print(name,result['replay'],result.get('error',''),flush=True)
(HERE/'real-replay.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
