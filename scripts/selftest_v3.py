#!/usr/bin/env python3
import json, tempfile, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def run(cmd,ok=True):
    r=subprocess.run(cmd,text=True,capture_output=True)
    if ok and r.returncode!=0: raise AssertionError((cmd,r.stdout,r.stderr))
    if not ok and r.returncode==0: raise AssertionError(('expected fail',cmd,r.stdout))
    return r
with tempfile.TemporaryDirectory() as td:
    td=Path(td); st=td/'manual.json'; p1=td/'01.png'; p2=td/'02.png'; p1.write_bytes(b'x'); p2.write_bytes(b'y')
    tool=ROOT/'scripts/manual_chain.py'
    run([sys.executable,str(tool),'init','--state',str(st),'--project-id','T','--minimum-pages','2'])
    run([sys.executable,str(tool),'add-prompt','--state',str(st),'--prompt-id','P1','--purpose','plan','--instruction','plan'])
    run([sys.executable,str(tool),'register-page','--state',str(st),'--page-id','01','--role','cover','--path',str(p1),'--batch-id','B1'])
    run([sys.executable,str(tool),'lock-anchor','--state',str(st),'--page-id','01'])
    run([sys.executable,str(tool),'add-prompt','--state',str(st),'--prompt-id','P2','--purpose','extension_batch','--instruction','extend','--input',str(p1)])
    run([sys.executable,str(tool),'register-page','--state',str(st),'--page-id','02','--role','principle','--path',str(p2),'--batch-id','B2','--depends-on','01'])
    d=json.loads(st.read_text()); d['phase']='manual_complete'; d['design_intent_package']='design_intent.json'; st.write_text(json.dumps(d))
    run([sys.executable,str(ROOT/'scripts/manual_chain_gate.py'),'--state',str(st)])
    di=td/'di.json'; eb=td/'eb.json'
    di.write_text(json.dumps({'product_identity':{'x':1},'modules':[1],'human_interactions':[1],'elements':[{'id':'x','classification':'visual_intent'}]}))
    eb.write_text(json.dumps({'product_architecture':1,'target_population':1,'kinematics':1,'task_envelope':1,'load_cases':[1],'assist_curve':1,'contact_interfaces':[1],'materials_and_processes':[1],'risk_register':[1],'facts_version':'1'}))
    run([sys.executable,str(ROOT/'scripts/cad_handoff_gate.py'),'--design-intent',str(di),'--engineering-baseline',str(eb)])
    manifest=td/'manifest.json'
    manifest.write_text(json.dumps({
      'design_intent':'di.json','parametric_source':['model.py'],'step_assemblies':['assembly.step'],'step_parts':['part.step'],
      'kinematics_reports':['kin.json'],'collision_reports':['col.json'],'cae_reports':['fea.json'],
      'dfm_dfa':['dfm.json'],'tolerance_gdt':['gdt.json'],'drawings':['a.pdf'],'bom':'bom.xlsx',
      'inspection_plan':'inspect.md','assembly_instructions':'assembly.md','release_manifest':'release.json',
      'physical_evidence':[],'owner_release':False
    }))
    run([sys.executable,str(ROOT/'scripts/production_release_gate.py'),'--manifest',str(manifest),'--target','C6'])
print('v3 selftest passed')
