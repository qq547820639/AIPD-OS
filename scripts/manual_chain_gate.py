#!/usr/bin/env python3
import argparse, json, subprocess, sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--state',required=True); ap.add_argument('--json-out'); a=ap.parse_args()
    tool=Path(__file__).with_name('manual_chain.py')
    r=subprocess.run([sys.executable,str(tool),'validate','--state',a.state],text=True,capture_output=True)
    try: report=json.loads(r.stdout)
    except Exception: report={"passed":False,"errors":[r.stderr or r.stdout]}
    d=json.loads(Path(a.state).read_text(encoding='utf-8'))
    report['manual_chain_planned']=any(p.get('purpose')=='plan' for p in d.get('prompts',[]))
    report['manual_anchors_locked']=bool(d.get('anchors'))
    report['manual_complete']=report.get('passed',False) and len(d.get('pages',[]))>=d.get('minimum_pages',10)
    report['design_intent_frozen']=report['manual_complete'] and bool(d.get('design_intent_package'))
    if a.json_out: Path(a.json_out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2)); raise SystemExit(0 if report['passed'] else 2)
if __name__=='__main__': main()
