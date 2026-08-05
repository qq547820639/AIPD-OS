#!/usr/bin/env python3
import argparse, json, hashlib
from pathlib import Path
from datetime import datetime, timezone


def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,d): Path(p).parent.mkdir(parents=True,exist_ok=True); Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(path):
    p=Path(path)
    if not p.exists() or not p.is_file(): return None
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def cmd_init(a):
    d={"schema_version":"1.0","project_id":a.project_id,"phase":"theory_ingested","minimum_pages":a.minimum_pages,"source_materials":[],"prompts":[],"pages":[],"anchors":[],"batches":[],"visual_bible":None,"design_intent_package":None,"facts_version":None,"created_at":now(),"updated_at":now()}
    save(a.state,d); print(json.dumps(d,ensure_ascii=False,indent=2))

def cmd_add_prompt(a):
    d=load(a.state); ins=a.input or []; outs=a.output or []
    item={"id":a.prompt_id,"purpose":a.purpose,"instruction":a.instruction,"inputs":ins,"outputs":outs,"status":a.status,"created_at":now()}
    d["prompts"]=[x for x in d["prompts"] if x.get("id")!=a.prompt_id]+[item]; d["updated_at"]=now(); save(a.state,d); print(json.dumps(item,ensure_ascii=False,indent=2))

def cmd_register_page(a):
    d=load(a.state); item={"page_id":a.page_id,"role":a.role,"path":a.path,"batch_id":a.batch_id,"depends_on":a.depends_on or [],"facts_version":a.facts_version,"status":a.status,"sha256":sha(a.path),"registered_at":now()}
    d["pages"]=[x for x in d["pages"] if x.get("page_id")!=a.page_id]+[item]
    batch=next((x for x in d["batches"] if x.get("id")==a.batch_id),None)
    if not batch: d["batches"].append({"id":a.batch_id,"pages":[a.page_id],"status":"in_progress"})
    elif a.page_id not in batch["pages"]: batch["pages"].append(a.page_id)
    d["updated_at"]=now(); save(a.state,d); print(json.dumps(item,ensure_ascii=False,indent=2))

def cmd_lock_anchor(a):
    d=load(a.state)
    ids={x.get('page_id') for x in d['pages']}
    if a.page_id not in ids: raise SystemExit(f'page not registered: {a.page_id}')
    if a.page_id not in d['anchors']: d['anchors'].append(a.page_id)
    d['phase']='anchors_locked'; d['updated_at']=now(); save(a.state,d); print(a.page_id)

def validate(d):
    errors=[]; warnings=[]
    prompt_ids=[x.get('id') for x in d.get('prompts',[])]
    if len(prompt_ids)!=len(set(prompt_ids)): errors.append('duplicate prompt id')
    page_ids=[x.get('page_id') for x in d.get('pages',[])]
    if len(page_ids)!=len(set(page_ids)): errors.append('duplicate page id')
    known=set(page_ids)
    for a in d.get('anchors',[]):
        if a not in known: errors.append(f'anchor page not registered: {a}')
    paths={str(x.get('path')) for x in d.get('pages',[]) if x.get('path')}
    for p in d.get('pages',[]):
        for dep in p.get('depends_on',[]):
            if dep not in known and dep not in paths: warnings.append(f"page {p.get('page_id')} dependency not registered: {dep}")
    purposes={x.get('purpose') for x in d.get('prompts',[])}
    if 'plan' not in purposes: errors.append('planning prompt missing')
    if d.get('phase') in {'anchors_locked','extension','manual_complete','design_intent_frozen'} and not d.get('anchors'): errors.append('anchors required for current phase')
    if d.get('phase') in {'manual_complete','design_intent_frozen'} and len(d.get('pages',[])) < int(d.get('minimum_pages',1)): errors.append('page count below minimum')
    # Attachment continuity: extension prompts must reference at least one registered page/anchor path.
    registered_paths={x.get('path') for x in d.get('pages',[]) if x.get('path')}
    anchor_paths={x.get('path') for x in d.get('pages',[]) if x.get('page_id') in set(d.get('anchors',[]))}
    for p in d.get('prompts',[]):
        if p.get('purpose') in {'extension_batch','extend','extension'}:
            if not set(p.get('inputs',[])) & (registered_paths|anchor_paths): errors.append(f"extension prompt {p.get('id')} does not include prior page attachment")
    return {"passed":not errors,"errors":errors,"warnings":warnings,"page_count":len(page_ids),"anchor_count":len(d.get('anchors',[])),"prompt_count":len(prompt_ids),"phase":d.get('phase')}

def cmd_validate(a):
    r=validate(load(a.state));
    if a.json_out: save(a.json_out,r)
    print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['passed'] else 2)

def cmd_status(a):
    d=load(a.state); r=validate(d); r['project_id']=d.get('project_id'); r['next_action']='plan' if not d.get('prompts') else ('generate_anchors' if not d.get('anchors') else ('extend_batches' if len(d.get('pages',[]))<d.get('minimum_pages',10) else 'assemble_and_freeze_design_intent'))
    print(json.dumps(r,ensure_ascii=False,indent=2))

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('init'); p.add_argument('--state',required=True); p.add_argument('--project-id',required=True); p.add_argument('--minimum-pages',type=int,default=10); p.set_defaults(f=cmd_init)
    p=sub.add_parser('add-prompt'); p.add_argument('--state',required=True); p.add_argument('--prompt-id',required=True); p.add_argument('--purpose',required=True); p.add_argument('--instruction',required=True); p.add_argument('--input',action='append'); p.add_argument('--output',action='append'); p.add_argument('--status',default='completed'); p.set_defaults(f=cmd_add_prompt)
    p=sub.add_parser('register-page'); p.add_argument('--state',required=True); p.add_argument('--page-id',required=True); p.add_argument('--role',required=True); p.add_argument('--path',required=True); p.add_argument('--batch-id',required=True); p.add_argument('--depends-on',action='append'); p.add_argument('--facts-version'); p.add_argument('--status',default='completed'); p.set_defaults(f=cmd_register_page)
    p=sub.add_parser('lock-anchor'); p.add_argument('--state',required=True); p.add_argument('--page-id',required=True); p.set_defaults(f=cmd_lock_anchor)
    p=sub.add_parser('validate'); p.add_argument('--state',required=True); p.add_argument('--json-out'); p.set_defaults(f=cmd_validate)
    p=sub.add_parser('status'); p.add_argument('--state',required=True); p.set_defaults(f=cmd_status)
    a=ap.parse_args(); a.f(a)
if __name__=='__main__': main()
