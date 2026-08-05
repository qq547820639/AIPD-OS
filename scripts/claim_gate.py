#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
CLAIMS={
 'theory_foundation_ready':['theory_foundation','evidence_register','risk_register'],
 'manual_complete':['manual_complete','manual_quality_report','page_lineage'],
 'engineering_model_ready':['cad_level_C3','parametric_source','kinematics_report','collision_report'],
 'prototype_build_ready':['cad_level_C6','drawings','bom','inspection_plan','owner_release'],
 'human_trial_ready':['prototype_test_evidence','risk_review','trial_protocol','owner_release'],
 'production_release_ready':['cad_level_C7','dvt_evidence','pvt_evidence','supplier_release','quality_plan','owner_release']}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--claim',required=True,choices=CLAIMS); p.add_argument('--json-out'); a=p.parse_args(); d=json.loads(Path(a.manifest).read_text(encoding='utf-8')); missing=[k for k in CLAIMS[a.claim] if not d.get(k)]
 out={'allowed':not missing,'claim':a.claim,'missing':missing,'reason':'evidence complete' if not missing else 'missing required evidence'}
 if a.json_out: Path(a.json_out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out['allowed'] else 1
if __name__=='__main__': sys.exit(main())
