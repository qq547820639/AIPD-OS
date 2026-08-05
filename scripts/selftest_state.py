#!/usr/bin/env python3
from __future__ import annotations
import json, tempfile
from pathlib import Path
from aipd_store import AIPDStore

def main():
 with tempfile.TemporaryDirectory() as d:
  s=AIPDStore(Path(d)/'state.sqlite'); s.init_project('TEST-001','Test Product','Test autonomous workflow')
  f=s.add_fact('target_mass','2.0','A','kg',confidence=.4,source='assumption')
  e=s.add_evidence('paper','Example paper',identifier='doi:test',quality='peer-reviewed')
  s.link_evidence(f,e)
  dec=s.propose_decision('Core route','Route A',[{'id':'A'},{'id':'B'}],'mutually exclusive route')
  assert s.project()['status']=='awaiting_owner_decision'
  s.resolve_decision(dec,'A','approved')
  assert s.project()['status']=='active'
  s.add_deliverable('project_brief',status='complete',gate='G0')
  assert not s.validate(), s.validate()
  payload=s.export(); assert payload['facts'][0]['value']=='2.0'; assert payload['decisions'][0]['choice']=='A'
 print('state self-test passed')
if __name__=='__main__': main()
