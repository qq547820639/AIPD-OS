#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
REQ={
 'S0_intake':['project_brief','truth_baseline','risk_register','work_plan'],
 'S1_theory':['theory_foundation','evidence_register','concept_options'],
 'S2_product_definition':['prd','system_architecture','v1_definition','initial_bom'],
 'S3_manual':['manual_plan','anchor_pages','manual_complete','design_intent_package'],
 'S4_engineering_baseline':['target_population','kinematics','load_cases','interfaces','materials','risk_register'],
 'S5_cad':['parametric_source','assembly_model','inspection_reports','drawings','cad_maturity_report'],
 'S6_industrialization':['bom','dfm_dfa','rfq_pack','supplier_plan','inspection_plan'],
 'S7_validation':['evt_plan','dvt_plan','pvt_plan','test_evidence'],
 'S8_release':['release_manifest','owner_release','change_log','quality_plan']}
def evaluate(manifest,phase):
 data=json.loads(Path(manifest).read_text(encoding='utf-8')); missing=[]
 for key in REQ[phase]:
  v=data.get(key)
  if v in (None,'',[],{},False): missing.append(key)
 return {'ok':not missing,'phase':phase,'missing':missing,'present':[k for k in REQ[phase] if k not in missing]}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--phase',required=True,choices=REQ); p.add_argument('--json-out'); a=p.parse_args(); out=evaluate(a.manifest,a.phase)
 if a.json_out: Path(a.json_out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out['ok'] else 1
if __name__=='__main__': sys.exit(main())
