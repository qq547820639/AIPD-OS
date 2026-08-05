#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from aipd_store import AIPDStore
from aipd_supervisor import Supervisor
from decision_policy import evaluate

def run(cmd,expect=0):
 r=subprocess.run(cmd,text=True,capture_output=True)
 if r.returncode!=expect: raise AssertionError((cmd,r.returncode,r.stdout,r.stderr))
 return r
with tempfile.TemporaryDirectory() as td:
 td=Path(td); db=td/'p.sqlite'; base=AIPDStore(db); base.init_project('T-001','test','deliver a product')
 sup=Supervisor(db); sup.init_lifecycle()
 w1=sup.add_work('S1_theory','research','build theory','evidence-backed theory',90)
 w2=sup.add_work('S2_product_definition','product','define v1','approved architecture',80,[w1])
 w3=sup.add_work('S3_manual','manual','plan manual','manual plan',70,[w2])
 assert sup.next_work()['work_id']==w1
 sup.complete(w1,{'theory':'theory.docx'})
 assert sup.next_work()['work_id']==w2
 sup.complete(w2,{'prd':'prd.docx'})
 assert sup.next_work()['work_id']==w3
 assert evaluate({'category':'ordinary_layout_fix'})['ask_owner'] is False
 assert evaluate({'category':'tooling_or_purchase','irreversible':True})['ask_owner'] is True
 sup.register_capability('faceted-step','available','local','C1')
 run([sys.executable,str(ROOT/'scripts/capability_gate.py'),'--ceiling','C1','--target','C3'],1)
 manifest=td/'life.json'; manifest.write_text(json.dumps({'project_brief':'a','truth_baseline':'b','risk_register':'c','work_plan':'d'}))
 run([sys.executable,str(ROOT/'scripts/lifecycle_gate.py'),'--manifest',str(manifest),'--phase','S0_intake'])
 claim=td/'claim.json'; claim.write_text(json.dumps({'manual_complete':1,'manual_quality_report':1,'page_lineage':1}))
 run([sys.executable,str(ROOT/'scripts/claim_gate.py'),'--manifest',str(claim),'--claim','manual_complete'])
 run([sys.executable,str(ROOT/'scripts/claim_gate.py'),'--manifest',str(claim),'--claim','production_release_ready'],1)
print('v4 supervisor selftest passed')
