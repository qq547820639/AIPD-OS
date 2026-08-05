#!/usr/bin/env python3
"""Run and validate a project-local parametric CAD generator."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--model-script',default='cad/model.py'); ap.add_argument('--json-out'); a=ap.parse_args()
 root=Path(a.project_root).resolve(); script=root/a.model_script
 report={'project_root':str(root),'script':str(script),'executed':False,'passed':False,'artifacts':{}}
 if not script.is_file(): report['error']='model script missing'
 else:
  cp=subprocess.run([sys.executable,str(script),'--output',str(root/'cad')],cwd=root,capture_output=True,text=True)
  report.update({'executed':True,'returncode':cp.returncode,'stdout':cp.stdout[-4000:],'stderr':cp.stderr[-4000:]})
  required=['cad/model.step','cad/model.stl','cad/model.glb','cad/inspection_report.json','cad/snapshot.png']
  report['artifacts']={p:(root/p).is_file() and (root/p).stat().st_size>0 for p in required}
  try: inspection=json.loads((root/'cad/inspection_report.json').read_text()); semantic=inspection.get('passed') is True
  except Exception: semantic=False
  report['inspection_passed']=semantic; report['passed']=cp.returncode==0 and all(report['artifacts'].values()) and semantic
 text=json.dumps(report,ensure_ascii=False,indent=2); print(text)
 if a.json_out: Path(a.json_out).write_text(text+'\n',encoding='utf-8')
 return 0 if report['passed'] else 3
if __name__=='__main__': raise SystemExit(main())
