#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path


def read_json(path:Path):
 try: return json.loads(path.read_text(encoding='utf-8'))
 except Exception: return None

def exists(root:Path, rel:str)->bool:
 p=root/rel; return p.is_file() and p.stat().st_size>0

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--json-out'); ap.add_argument('--require',choices=['artifact','communication','engineering','prototype','production'],default='communication')
 a=ap.parse_args(); root=Path(a.project_root)
 contract=read_json(root/'quality/outcome_contract.json')
 manual=read_json(root/'manual/manual_quality_review.json')
 cad=read_json(root/'cad/cad_maturity_report.json')
 artifacts=['requirements/requirements.md','engineering/v1_engineering.md','manual/manual.pdf']
 artifact_complete=all(exists(root,x) for x in artifacts)
 digital_thread_complete=artifact_complete and exists(root,'state/project_checkpoint.json') and exists(root,'cad/model.step') and exists(root,'cad/inspection_report.json') and exists(root,'manufacturing/bom.xlsx')
 communication_accepted=bool(digital_thread_complete and contract is not None and manual and manual.get('golden_reference_compared') and manual.get('owner_or_independent_visual_acceptance') and manual.get('score',0)>=manual.get('threshold',8.0))
 engineering_model_ready=bool(cad and cad.get('target_passed') and cad.get('reached_level') in ['CAD-L3','CAD-L4','CAD-L5'])
 prototype_build_ready=bool(cad and cad.get('claims',{}).get('prototype_build_ready'))
 production_release_ready=bool(cad and cad.get('claims',{}).get('production_release_ready') and exists(root,'release/production_approval.json'))
 states={'artifact':artifact_complete,'communication':communication_accepted,'engineering':engineering_model_ready,'prototype':prototype_build_ready,'production':production_release_ready}
 result={'project_root':str(root.resolve()),'artifact_complete':artifact_complete,'digital_thread_complete':digital_thread_complete,
         'communication_accepted':communication_accepted,'engineering_model_ready':engineering_model_ready,
         'prototype_build_ready':prototype_build_ready,'production_release_ready':production_release_ready,
         'requested_gate':a.require,'requested_gate_passed':states[a.require],
         'classification':('production_release_ready' if production_release_ready else 'prototype_build_ready' if prototype_build_ready else 'engineering_model_ready' if engineering_model_ready else 'communication_accepted' if communication_accepted else 'digital_thread_complete_but_outcome_not_accepted' if digital_thread_complete else 'not_complete')}
 text=json.dumps(result,ensure_ascii=False,indent=2); print(text)
 if a.json_out: Path(a.json_out).write_text(text+'\n',encoding='utf-8')
 return 0 if result['requested_gate_passed'] else 5
if __name__=='__main__': raise SystemExit(main())
