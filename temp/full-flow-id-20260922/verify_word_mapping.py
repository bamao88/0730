"""Prototype mapping audit of real initial inventories, no semantic decisions or writes."""
import importlib.util,json,sys
from pathlib import Path
from docfit.template.materialization.runtime import _fragment_text_is_current
from docfit.template.source_spans import resolve_source_span,SourceSpan,TextSourceExtent,WholeEntrySourceExtent
p=Path('temp/full-flow-id-20260922/source_package.py');spec=importlib.util.spec_from_file_location('source_package_probe',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
base=Path('temp/full-flow-id-20260922');results=[]
for name in ('hunau-initial-read-proof','njau-initial-read-proof','pku-initial-read-proof'):
 r=base/name;pkg=m.SourceWordPackage.load(r/'input/school-template.docx');initial=json.loads((r/'work/.docfit/initial-source-inventory.json').read_text());canonical=initial['canonical_source_inventory']
 inv={'document_sha256':canonical['source_snapshot_sha256'],'canonical_source_inventory':canonical,'source_entries':canonical['source_entries']}
 failed=[];count=0
 for entry in canonical['source_entries']:
  extent=TextSourceExtent(0,len(entry['text'])) if entry['text'] else WholeEntrySourceExtent()
  try:resolved=resolve_source_span(inventory=inv,source_span=SourceSpan(entry['source_entry_id'],extent))
  except Exception as e:failed.append({'source_entry_id':entry['source_entry_id'],'error':str(e)});continue
  for fragment in resolved.word_fragments:
   f=fragment.to_json();count+=1;n=pkg.resolve(f['locator'])
   if n is None or not _fragment_text_is_current(n,f):failed.append({'locator':f['locator'],'expected':f['text'],'resolved':n is not None})
 result={'input':name,'source_sha256':canonical['source_snapshot_sha256'],'fragments':count,'failed':failed,'level':'prototype package mapping against actual Word XML, no Agent/write acceptance'};results.append(result)
 print(name,'fragments',count,'failures',len(failed),failed[:3],flush=True)
 (base/'word-mapping-prototype.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
