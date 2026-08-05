#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
MANDATORY={'product_architecture_fork','brand_value_judgment','key_interface_freeze','safety_or_regulatory','human_trial','formal_drawing_release','tooling_or_purchase','production_release','hard_constraint_conflict','ip_or_claim_risk'}
def evaluate(event):
 reasons=[]
 cat=event.get('category')
 if cat in MANDATORY: reasons.append(f'category:{cat}')
 if event.get('irreversible'): reasons.append('irreversible')
 if event.get('external_commitment'): reasons.append('external_commitment')
 if event.get('safety_impact') in {'high','critical'}: reasons.append('safety')
 if event.get('regulatory_impact') in {'high','critical'}: reasons.append('regulatory')
 if event.get('value_judgment'): reasons.append('owner_value_judgment')
 if event.get('hard_constraint_conflict'): reasons.append('hard_constraint_conflict')
 cost=float(event.get('cost_impact',0) or 0); threshold=float(event.get('owner_cost_threshold',1e30) or 1e30)
 if cost>=threshold: reasons.append('cost_threshold')
 ask=bool(reasons)
 return {'ask_owner':ask,'reasons':reasons,'default_action':'submit_decision_package' if ask else event.get('safe_default','continue_autonomously')}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--event',required=True); p.add_argument('--json-out'); a=p.parse_args(); event=json.loads(Path(a.event).read_text()) if False else json.loads(a.event)
 out=evaluate(event)
 if a.json_out: open(a.json_out,'w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
 print(json.dumps(out,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': sys.exit(main())
