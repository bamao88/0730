from pathlib import Path
import json
from docfit.app.prepare_template import PrepareTemplateRequest, prepare_template_task, _post_unit_inventory_from_checkpoint, _select_host_candidate_for_accepted_semantics
from docfit.template.harness import TemplateHarnessService
from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import publication_slot_protocol_status
from docfit.tools.runtime import sha256_file

old=Path('temp/source-entry-real-replay-20260905-103825').resolve()
root=Path('temp/id-closure-20260911/slot-replay-final').resolve()
prepared=prepare_template_task(PrepareTemplateRequest(school_template=old/'input/school-template.docx',field_registry=old/'input/field-registry.yaml',output_directory=root))
checkpoint=json.loads((old/'work/.docfit/unit-boundary-checkpoint.json').read_text())
assert checkpoint['source_hash']==prepared.template_sha256
(root/'work/.docfit/unit-boundary-checkpoint.json').write_text(json.dumps(checkpoint))
inventory=_post_unit_inventory_from_checkpoint(prepared,checkpoint)
harness=TemplateHarnessService(task_root=root)
accepted_inventory=harness.handle({'action':'submit_object_inventory','document_sha256':inventory['document_sha256'],'objects':inventory['objects'],'reading_blocks':inventory['reading_blocks'],'source_entries':inventory['source_entries']})
assert accepted_inventory['status']=='ok',accepted_inventory
prior=json.loads((old/'work/.docfit/harness/semantic-judgments.json').read_text())
judgments=[{k:j[k] for k in ['source_entry_id','parts']} for j in prior['semantic_judgments']]
review=harness.handle({'action':'submit_semantic_judgments','document_sha256':prepared.template_sha256,'semantic_judgments':judgments})
assert review['status']=='ok',review
candidate=_select_host_candidate_for_accepted_semantics(prepared)
protocol=publication_slot_protocol_status(candidate_docx=candidate, registry=FieldRegistrySnapshot.load(prepared.registry_source))
assert protocol['status']=='ok',protocol
proof={'verification_level':'real replay','source_hash':prepared.template_sha256,'judgment_source':str(old/'work/.docfit/harness/semantic-judgments.json'),'source_entry_count':len(inventory['source_entries']),'inventory_status':accepted_inventory['status'],'review_status':review['status'],'candidate':str(candidate),'candidate_hash':sha256_file(candidate),'slot_protocol':protocol,'limitations':['No live Agent in this replay','No publication or visual acceptance claimed']}
(root/'replay-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(proof,ensure_ascii=False,indent=2))
