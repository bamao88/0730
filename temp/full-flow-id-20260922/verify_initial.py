import json
from pathlib import Path
from docfit.app.prepare_template import PrepareTemplateRequest, prepare_template_task
from docfit.tools.service import DocFitToolService
from docfit.tools.runtime import sha256_file
from docfit.template.unit_source import load_initial_inventory
base=Path('temp/full-flow-id-20260922')
rows=[]
for school in ('hunau','njau','pku'):
 src=next(Path('temp/manual-gold-preparation/gold/00-inputs/schools').glob(school+'*source-template.docx'))
 prepared=prepare_template_task(PrepareTemplateRequest(school_template=src,output_directory=base/(school+'-initial-read-proof')))
 initial=load_initial_inventory(prepared.task_root,prepared.template_sha256)
 expected=[e['source_entry_id'] for e in initial['canonical_source_inventory']['source_entries']]
 service=DocFitToolService(task_root=prepared.task_root)
 results=[]
 for limit in (3,17,200):
  seen=[];offset=0;windows=0
  while True:
   card=service.evidence({'focus':'document_map','offset':offset,'limit':limit})
   summary=card['summary'];seen.extend(e['source_entry_id'] for e in summary['source_entries']);windows+=1
   window=summary['source_entry_window']
   if not window['has_more']:break
   offset=window['next_offset']
  assert seen==expected,(len(seen),len(expected))
  results.append({'limit':limit,'windows':windows,'same_ordered_ids':True})
 assert load_initial_inventory(prepared.task_root,prepared.template_sha256)==initial
 report={'school':school,'verification_level':'real input preparation and Tool projection only; no Agent or write proof','source_sha256':prepared.template_sha256,'initial_inventory_digest':initial['canonical_source_inventory']['inventory_digest'],'entry_count':len(expected),'windows':results,'source_unchanged':sha256_file(prepared.template_path)==prepared.template_sha256}
 rows.append(report)
 (base/'initial-read-proof.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(report),flush=True)
