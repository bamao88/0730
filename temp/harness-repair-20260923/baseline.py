import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from docfit.app import prepare_template as app
from docfit.template import semantic_batches as batches
from docfit.template.harness import _decode_whitespace_parts
from docfit.template.source_spans import resolve_semantic_judgments, SourceSpanResolutionError
from docfit.tools.runtime import sha256_file
from tests.contract.test_semantic_batches import _inventory_and_checkpoint, _complete_output
from tests.contract.test_prepare_template_runtime import _prepared

root = Path('temp/harness-repair-20260923')
report = {'code_commit': '5ba6a29', 'level': 'logic/contract plus explicitly marked real replay', 'probes': {}}
inv, checkpoint, ids = _inventory_and_checkpoint()
manifest = batches.build_semantic_batch_manifest(inventory=inv, checkpoint=checkpoint)
batch = manifest.batches[0]
output = _complete_output(batch.source_entry_ids, summary='baseline')
output['semantic_judgments'][0]['parts'] = [{'text':'姓名：', 'role':'fixed_label'}]
ledger = batches.record_semantic_batch_candidate(manifest=manifest, ledger=batches.SemanticBatchCandidateLedger.empty(manifest), batch_id=batch.batch_id, structured_output=output, allowed_field_ids=())
repaired, repaired_ids = batches.repair_uniform_responsibility_text_revisions(manifest=manifest,ledger=ledger,source_entry_text_by_id={ids[0]:'姓名：张三'},source_entry_ids=(ids[0],),allowed_field_ids=())
report['probes']['A'] = {'input_type':'constructed','before':output['semantic_judgments'][0], 'after':repaired.candidates[0].semantic_judgments[0]}
feedback={'blockers':[{'code':'ordered_part_text_gap','source_entry_id':ids[0],'message':'Missing source text.'}]}
prompt=app.build_semantic_batch_prompt(manifest=manifest,batch=batch,feedback=feedback,editable_source_entry_ids=(ids[0],),responsibility_locked_source_entry_ids=(ids[0],))
report['probes']['C']={'requires_prior_role':'keep each prior role' in prompt,'contains_prior_role':'fixed_label' in prompt,'contains_prior_text':'姓名：' in prompt}
report['probes']['E']=app._agent_visible_feedback_packet({'blockers':[{'code':'scope_invalid','source_entry_id':ids[0],'message':'The locator cannot resolve the source entry.'}]},next_step='Revise listed entries.')
with tempfile.TemporaryDirectory() as directory:
    prepared=_prepared(Path(directory))
    with patch.object(app.DocFitToolService, 'validate', return_value={'checks': []}) as validate:
        visual, validation = app._validate_host_candidate(prepared,prepared.template_path)
        report['probes']['F']={'level':'logic/contract; mocked objective validation','visual':visual,'validation_args':validate.call_args.args[0]}

real=Path('temp/span-skill-e2e-20260922-87710163/body-task')
harness=real/'work/.docfit/harness'
load=lambda p:json.loads(p.read_text())
inv=load(harness/'object-inventory.json')
proof=load(real/'work/.docfit/unit-boundary-checkpoint.json')
manifest=batches.build_semantic_batch_manifest(inventory=inv,checkpoint=proof)
ledger_path=harness/'semantic-batch-candidates.json'
allowed=tuple(inv['field_id_vocabulary']['allowed_field_ids'])
ledger=batches.SemanticBatchCandidateLedger.from_json(load(ledger_path),manifest=manifest,allowed_field_ids=allowed)
output=batches.aggregate_semantic_batch_candidates(manifest=manifest,ledger=ledger)
decoded, feedback=_decode_whitespace_parts(output['semantic_judgments'])
assert feedback is None
assert sha256_file(real/'input/school-template.docx') == inv['document_sha256']
try:
    resolve_semantic_judgments(inventory=inv,judgments=decoded)
    blockers=[]
except SourceSpanResolutionError as e:
    blockers=e.blockers
report['real_replay']={'task_root':str(real),'source_sha256':inv['document_sha256'],'ledger_sha256':sha256_file(ledger_path),'judgment_count':len(decoded),'blockers':blockers,'all_rejected_turns_available':False}
inputs=[]
source_root=Path('temp/manual-gold-preparation/gold/00-inputs/schools')
registry=Path('docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml')
for school in ('hunau-undergraduate','njau-undergraduate','pku-graduate'):
    source=source_root/f'{school}__source-template.docx'
    dest=root/'inputs'/school/'school-template.docx'
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,dest)
    shutil.copyfile(registry,dest.parent/'field-registry.yaml')
    inputs.append({'school':school,'source_path':str(source),'frozen_input':str(dest),'source_sha256':sha256_file(dest),'registry_sha256':sha256_file(registry)})
report['frozen_inputs']=inputs
(root/'baseline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'baseline':str(root/'baseline.json'),'probes':list(report['probes']),'real_replay_blockers':len(blockers),'judgments':len(decoded),'frozen_schools':len(inputs)},ensure_ascii=False))
