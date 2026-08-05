#!/usr/bin/env python3
import argparse, json
from pathlib import Path

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def present(v): return v not in (None,'',[],{})
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--design-intent',required=True); ap.add_argument('--engineering-baseline',required=True); ap.add_argument('--json-out'); a=ap.parse_args()
    di=load(a.design_intent); eb=load(a.engineering_baseline)
    req_di=['product_identity','modules','human_interactions','elements']
    req_eb=['product_architecture','target_population','kinematics','task_envelope','load_cases','assist_curve','contact_interfaces','materials_and_processes','risk_register','facts_version']
    missing_di=[x for x in req_di if not present(di.get(x))]
    missing_eb=[x for x in req_eb if not present(eb.get(x))]
    invalid=[]
    allowed={'engineering_confirmed','visual_intent','engineering_required','narrative_only','prohibited'}
    for e in di.get('elements',[]):
        if e.get('classification') not in allowed: invalid.append(e.get('id') or e.get('name') or 'unknown')
    r={"passed":not(missing_di or missing_eb or invalid),"cad_handoff_ready":not(missing_di or missing_eb or invalid),"missing_design_intent":missing_di,"missing_engineering_baseline":missing_eb,"invalid_element_classifications":invalid}
    if a.json_out: Path(a.json_out).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['passed'] else 2)
if __name__=='__main__': main()
