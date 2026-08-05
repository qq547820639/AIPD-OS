#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aipd_store import AIPDStore


def parse_json(value: str):
    try: return json.loads(value)
    except json.JSONDecodeError as exc: raise argparse.ArgumentTypeError(str(exc))


def build_parser():
    p=argparse.ArgumentParser(description='Manage AIPD project state.')
    sub=p.add_subparsers(dest='cmd',required=True)
    def dbarg(sp): sp.add_argument('--db',required=True)

    s=sub.add_parser('init'); dbarg(s); s.add_argument('--project-id',required=True); s.add_argument('--name',required=True); s.add_argument('--goal',required=True); s.add_argument('--owner-policy',default='AI executes; owner reviews decisions only')
    s=sub.add_parser('summary'); dbarg(s)
    s=sub.add_parser('add-fact'); dbarg(s); s.add_argument('--key',required=True); s.add_argument('--value',required=True); s.add_argument('--value-json',action='store_true'); s.add_argument('--status',required=True); s.add_argument('--unit'); s.add_argument('--tolerance'); s.add_argument('--conditions'); s.add_argument('--confidence',type=float,default=.5); s.add_argument('--source'); s.add_argument('--version')
    s=sub.add_parser('add-evidence'); dbarg(s); s.add_argument('--kind',required=True); s.add_argument('--title',required=True); s.add_argument('--url'); s.add_argument('--identifier'); s.add_argument('--quality'); s.add_argument('--summary'); s.add_argument('--metadata-json',type=parse_json,default={})
    s=sub.add_parser('link-evidence'); dbarg(s); s.add_argument('--fact-id',required=True); s.add_argument('--evidence-id',required=True); s.add_argument('--relation',default='supports')
    s=sub.add_parser('propose-decision'); dbarg(s); s.add_argument('--topic',required=True); s.add_argument('--recommendation',required=True); s.add_argument('--options-json',type=parse_json,required=True); s.add_argument('--trigger')
    s=sub.add_parser('resolve-decision'); dbarg(s); s.add_argument('--decision-id',required=True); s.add_argument('--choice',required=True); s.add_argument('--comment')
    s=sub.add_parser('add-deliverable'); dbarg(s); s.add_argument('--type',required=True); s.add_argument('--path'); s.add_argument('--status',default='planned'); s.add_argument('--version'); s.add_argument('--gate'); s.add_argument('--metadata-json',type=parse_json,default={})
    s=sub.add_parser('add-risk'); dbarg(s); s.add_argument('--title',required=True); s.add_argument('--probability'); s.add_argument('--impact'); s.add_argument('--mitigation'); s.add_argument('--status',default='open'); s.add_argument('--trigger')
    s=sub.add_parser('set-gate'); dbarg(s); s.add_argument('--gate',required=True); s.add_argument('--status'); s.add_argument('--version')
    s=sub.add_parser('add-dependency'); dbarg(s); s.add_argument('--source-type',required=True); s.add_argument('--source-id',required=True); s.add_argument('--target-type',required=True); s.add_argument('--target-id',required=True); s.add_argument('--relation',default='affects')
    s=sub.add_parser('impact'); dbarg(s); s.add_argument('--source-type',required=True); s.add_argument('--source-id',required=True)
    s=sub.add_parser('validate'); dbarg(s)
    s=sub.add_parser('export'); dbarg(s); s.add_argument('--out',required=True)
    return p


def main():
    a=build_parser().parse_args(); store=AIPDStore(a.db)
    if a.cmd=='init': store.init_project(a.project_id,a.name,a.goal,a.owner_policy); result={'ok':True,'project_id':a.project_id}
    elif a.cmd=='summary': result=store.summary()
    elif a.cmd=='add-fact':
        value=json.loads(a.value) if a.value_json else a.value
        result={'fact_id':store.add_fact(a.key,value,a.status,a.unit,a.tolerance,a.conditions,a.confidence,a.source,a.version)}
    elif a.cmd=='add-evidence': result={'evidence_id':store.add_evidence(a.kind,a.title,a.url,a.identifier,a.quality,a.summary,a.metadata_json)}
    elif a.cmd=='link-evidence': store.link_evidence(a.fact_id,a.evidence_id,a.relation); result={'ok':True}
    elif a.cmd=='propose-decision': result={'decision_id':store.propose_decision(a.topic,a.recommendation,a.options_json,a.trigger)}
    elif a.cmd=='resolve-decision': store.resolve_decision(a.decision_id,a.choice,a.comment); result={'ok':True}
    elif a.cmd=='add-deliverable': result={'deliverable_id':store.add_deliverable(a.type,a.path,a.status,a.version,a.gate,a.metadata_json)}
    elif a.cmd=='add-risk': result={'risk_id':store.add_risk(a.title,a.probability,a.impact,a.mitigation,a.status,a.trigger)}
    elif a.cmd=='set-gate': store.set_gate(a.gate,a.status,a.version); result={'ok':True}
    elif a.cmd=='add-dependency': store.add_dependency(a.source_type,a.source_id,a.target_type,a.target_id,a.relation); result={'ok':True}
    elif a.cmd=='impact': result=store.impact(a.source_type,a.source_id)
    elif a.cmd=='validate':
        errors=store.validate(); result={'ok':not errors,'errors':errors}
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if not errors else 1
    elif a.cmd=='export':
        Path(a.out).write_text(json.dumps(store.export(),ensure_ascii=False,indent=2),encoding='utf-8'); result={'ok':True,'out':a.out}
    else: raise AssertionError(a.cmd)
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': sys.exit(main())
