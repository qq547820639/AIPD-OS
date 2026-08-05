#!/usr/bin/env python3
"""Runtime capability check. Capability is not project closure."""
from __future__ import annotations
import argparse, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

def command_version(cmd):
 exe=shutil.which(cmd)
 if not exe:return {'found':False,'path':None,'version':None}
 try:
  cp=subprocess.run([exe,'--version'],capture_output=True,text=True,timeout=15); lines=(cp.stdout or cp.stderr).strip().splitlines()
  return {'found':True,'path':exe,'version':lines[0] if lines else None,'returncode':cp.returncode}
 except Exception as e:return {'found':True,'path':exe,'error':str(e)}

def inspect_plugin(paths):
 for candidate in paths:
  if not candidate:continue
  root=Path(candidate).expanduser()
  for skill in [root,root/'skills/cad',root/'.agents/skills/cad']:
   if (skill/'SKILL.md').is_file():
    return {'detected':True,'path':str(skill.resolve()),'tools':{n:(skill/'scripts'/n).exists() for n in ('step','inspect','snapshot')}}
 return {'detected':False,'path':None,'tools':{}}

def has_module(name):return importlib.util.find_spec(name) is not None

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--skill-root',default=str(Path(__file__).resolve().parents[1])); ap.add_argument('--cad-skill-dir',default=os.getenv('AIPD_CAD_SKILL_DIR')); ap.add_argument('--json-out'); ap.add_argument('--require-any-cad',action='store_true'); a=ap.parse_args()
 root=Path(a.skill_root).resolve(); architecture_files=['SKILL.md','scripts/aipd_state.py','scripts/aipd_store.py','scripts/cad_convergence.py','scripts/e2e_acceptance.py','references/cad-production-pipeline.md']
 architecture={f:(root/f).is_file() for f in architecture_files}; codex=command_version('codex')
 plugin=inspect_plugin([a.cad_skill_dir,Path.cwd()/'.agents/skills/cad',Path.home()/'.agents/skills/cad',Path.home()/'.codex/plugins/text-to-cad/skills/cad'])
 local_brep={'available':has_module('build123d') and has_module('OCP'),'modules':{'build123d':has_module('build123d'),'OCP':has_module('OCP')}}
 local_faceted={'available':all(has_module(m) for m in ('trimesh','numpy','matplotlib')),'modules':{m:has_module(m) for m in ('trimesh','numpy','matplotlib')},'max_release_level':'C1 internal digital prototype'}
 modes=[]
 if plugin['detected']:modes.append('provider_cad_skill')
 if local_brep['available']:modes.append('local_native_brep')
 if local_faceted['available']:modes.append('local_faceted_brep')
 report={'architecture_ready':all(architecture.values()),'architecture_files':architecture,'python':{'version':sys.version.split()[0]},'codex':codex,'provider_plugin':plugin,'local_native_brep':local_brep,'local_faceted_brep':local_faceted,'available_cad_modes':modes,'cad_runtime_capable':bool(modes),'state_runtime_ready':(root/'scripts/aipd_state.py').is_file() and (root/'scripts/aipd_store.py').is_file()}
 report['classification']='runtime_capable' if report['architecture_ready'] and report['state_runtime_ready'] and report['cad_runtime_capable'] else ('architecture_closed' if report['architecture_ready'] else 'not_ready')
 report['full_digital_chain_ready']=False; report['note']='Project closure requires real project artifacts and e2e_acceptance.py; preflight never declares closure.'
 text=json.dumps(report,ensure_ascii=False,indent=2); print(text)
 if a.json_out:Path(a.json_out).write_text(text+'\n',encoding='utf-8')
 return 0 if (not a.require_any_cad or report['cad_runtime_capable']) else 2
if __name__=='__main__':raise SystemExit(main())
