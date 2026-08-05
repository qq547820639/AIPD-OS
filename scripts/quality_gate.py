#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from aipd_store import AIPDStore

# Kept dependency-free: requirements mirror assets/templates/gate_requirements.yaml.
REQ={
'G0':['project_brief','material_index','initial_fact_register','execution_map'],
'G1':['scenario_model','requirement_definition','non_goals','initial_risk_register'],
'G2':['concept_comparison','recommended_route','v1_value_test'],
'G3':['v1_engineering_definition','preliminary_bom','interface_register','dfmea_draft'],
'G4':['simulation_or_calculation_plan','result_or_execution_package','parameter_register'],
'G5':['product_specification','bom','key_parameter_table','supply_chain_plan','rfq_package','dfm_dfa_review'],
'G6':['evt_plan','evt_raw_data','evt_report','issue_register'],
'G7':['dvt_plan','dvt_raw_data','dvt_report','compliance_status'],
'G8':['pvt_plan','process_capability','quality_control_plan','mass_production_recommendation'],
'G9':['product_manual','release_package','release_audit','project_checkpoint']}
OWNER={'G2','G5','G6','G7','G8','G9'}

def main():
 p=argparse.ArgumentParser(); p.add_argument('--db',required=True); p.add_argument('--gate'); a=p.parse_args()
 s=AIPDStore(a.db); project=s.project(); gate=a.gate or project['gate']; errors=s.validate()
 deliverables=s.rows('deliverables'); complete={d['type'] for d in deliverables if d['status'] in {'complete','approved','released'}}
 missing=[x for x in REQ[gate] if x not in complete]
 proposed=[d for d in s.rows('decisions') if d['status']=='proposed']
 result={'gate':gate,'pass':not errors and not missing and not proposed,'missing_deliverables':missing,'state_errors':errors,'open_decisions':[d['decision_id'] for d in proposed],'owner_approval_required':gate in OWNER}
 print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result['pass'] else 1
if __name__=='__main__': sys.exit(main())
