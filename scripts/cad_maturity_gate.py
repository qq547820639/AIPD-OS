#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

LEVELS=['CAD-L0','CAD-L1','CAD-L2','CAD-L3','CAD-L4','CAD-L5']

REQUIREMENTS={
 'CAD-L0':['coordinate_system','human_environment_envelopes','overall_dimensions'],
 'CAD-L1':['architecture_layout','load_path_concept','interface_placeholders'],
 'CAD-L2':['native_parametric_brep','editable_feature_tree','real_part_features','material_process_intent'],
 'CAD-L3':['assembly_constraints','kinematic_model','anthropometric_family','standard_components','continuous_rom_clearance','fasteners_bearings_stops'],
 'CAD-L4':['load_cases','strength_stiffness_evidence','fatigue_plan_or_evidence','dfm_dfa','datum_scheme','gdt','tolerance_stack','complete_drawings','inspection_characteristics'],
 'CAD-L5':['model_drawing_bom_same_revision','supplier_review','prototype_measurement','dvt_evidence','pvt_control_plan']
}

RUNTIME_MAX={'mesh':'CAD-L0','faceted_brep':'CAD-L1','native_brep':'CAD-L4','provider_native_cad':'CAD-L5'}


def idx(level:str)->int: return LEVELS.index(level)

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True); ap.add_argument('--json-out'); ap.add_argument('--target',default='CAD-L3',choices=LEVELS)
 a=ap.parse_args(); m=json.loads(Path(a.manifest).read_text(encoding='utf-8'))
 runtime=m.get('runtime','mesh'); evidence=m.get('evidence',{})
 reached='CAD-L0'; level_checks={}
 runtime_max=RUNTIME_MAX.get(runtime,'CAD-L0')
 cumulative=[]
 for level in LEVELS:
  cumulative+=REQUIREMENTS[level]
  checks={k:bool(evidence.get(k)) for k in cumulative}
  passed=all(checks.values()) and idx(level)<=idx(runtime_max)
  level_checks[level]={'passed':passed,'checks':checks,'runtime_allowed':idx(level)<=idx(runtime_max)}
  if passed: reached=level
  else: break
 target_passed=idx(reached)>=idx(a.target)
 result={'runtime':runtime,'runtime_max_level':runtime_max,'reached_level':reached,'target_level':a.target,
         'target_passed':target_passed,'level_checks':level_checks,
         'claims':{
          'wearable_human_ready': bool(evidence.get('human_fit_validation') and evidence.get('risk_controls_validated') and idx(reached)>=idx('CAD-L4')),
          'prototype_build_ready': bool(target_passed and idx(reached)>=idx('CAD-L4')),
          'production_release_ready': bool(idx(reached)>=idx('CAD-L5')),
         }}
 text=json.dumps(result,ensure_ascii=False,indent=2); print(text)
 if a.json_out: Path(a.json_out).write_text(text+'\n',encoding='utf-8')
 return 0 if target_passed else 4
if __name__=='__main__': raise SystemExit(main())
