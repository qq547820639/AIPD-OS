#!/usr/bin/env python3
import argparse, json
from pathlib import Path
LEVELS=['C0','C1','C2','C3','C4','C5','C6','C7']
REQ={
'C0':['design_intent'],
'C1':['parametric_source','step_assemblies'],
'C2':['parametric_source','step_parts'],
'C3':['kinematics_reports','collision_reports'],
'C4':['cae_reports'],
'C5':['dfm_dfa','tolerance_gdt'],
'C6':['drawings','bom','inspection_plan','assembly_instructions','release_manifest'],
'C7':['physical_evidence','owner_release']}
def present(v): return v is True or v not in (None,'',[],{})
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True); ap.add_argument('--target',choices=LEVELS,required=True); ap.add_argument('--json-out'); a=ap.parse_args()
    d=json.loads(Path(a.manifest).read_text(encoding='utf-8')); idx=LEVELS.index(a.target); missing=[]
    for level in LEVELS[:idx+1]:
        for k in REQ.get(level,[]):
            if not present(d.get(k)): missing.append(f'{level}:{k}')
    r={"passed":not missing,"target":a.target,"achieved":a.target if not missing else LEVELS[max(0,next((i for i,l in enumerate(LEVELS[:idx+1]) if any(x.startswith(l+':') for x in missing)),0)-1)],"missing":missing,"production_release_ready":a.target=='C7' and not missing,"prototype_build_ready":idx>=6 and not missing}
    if a.json_out: Path(a.json_out).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['passed'] else 2)
if __name__=='__main__': main()
