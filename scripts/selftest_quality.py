#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(cmd):
 return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)

def main()->int:
 failures=[]
 with tempfile.TemporaryDirectory() as td:
  t=Path(td); (t/'quality').mkdir(); (t/'manual').mkdir(); (t/'cad').mkdir(); (t/'requirements').mkdir(); (t/'engineering').mkdir()
  for rel in ['requirements/requirements.md','engineering/v1_engineering.md','manual/manual.pdf']:
   (t/rel).write_text('x',encoding='utf-8')
  (t/'quality/outcome_contract.json').write_text('{}')
  # old-style artifact-only project must fail communication gate
  r=run([sys.executable,str(ROOT/'scripts/outcome_acceptance.py'),'--project-root',str(t),'--require','communication'])
  if r.returncode==0: failures.append('artifact-only project incorrectly passed communication acceptance')
  # faceted BREP cannot reach C7
  manifest={'runtime':'faceted_brep','evidence':{k:True for v in __import__('runpy').run_path(str(ROOT/'scripts/cad_maturity_gate.py'))['REQUIREMENTS'].values() for k in v}}
  p=t/'cad_manifest.json'; p.write_text(json.dumps(manifest))
  r=run([sys.executable,str(ROOT/'scripts/cad_maturity_gate.py'),'--manifest',str(p),'--target','C7'])
  if r.returncode==0: failures.append('faceted BREP incorrectly passed C7')
 print(json.dumps({'passed':not failures,'failures':failures},ensure_ascii=False,indent=2))
 return 0 if not failures else 6
if __name__=='__main__': raise SystemExit(main())
