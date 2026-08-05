#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sqlite3, sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import aipd_os  # noqa: F401
except ImportError:
    # 独立运行脚本时，若包未 pip 安装，则将仓库 src/ 加入 sys.path
    _src = Path(__file__).resolve().parent.parent / 'src'
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
PHASES=['S0_intake','S1_theory','S2_product_definition','S3_manual','S4_engineering_baseline','S5_cad','S6_industrialization','S7_validation','S8_release']
WORK_STATUSES={'queued','ready','running','blocked_external','blocked_decision','internal_rework','complete','cancelled'}
SCHEMA=r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS supervisor_work_items(
 work_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, phase TEXT NOT NULL, module TEXT NOT NULL,
 title TEXT NOT NULL, objective TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 50,
 status TEXT NOT NULL DEFAULT 'queued', owner_required INTEGER NOT NULL DEFAULT 0,
 decision_id TEXT, depends_on_json TEXT NOT NULL DEFAULT '[]', inputs_json TEXT NOT NULL DEFAULT '{}',
 outputs_json TEXT NOT NULL DEFAULT '{}', acceptance_json TEXT NOT NULL DEFAULT '{}',
 capability_floor TEXT, blocked_reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supervisor_phase_runs(
 run_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, phase TEXT NOT NULL, status TEXT NOT NULL,
 entry_checks_json TEXT NOT NULL DEFAULT '{}', exit_checks_json TEXT NOT NULL DEFAULT '{}',
 started_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE IF NOT EXISTS supervisor_capabilities(
 capability_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, provider TEXT,
 status TEXT NOT NULL, maturity_ceiling TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supervisor_reviews(
 review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL,
 review_type TEXT NOT NULL, result TEXT NOT NULL, findings_json TEXT NOT NULL DEFAULT '[]', reviewer TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supervisor_lineage(
 lineage_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
 upstream_type TEXT NOT NULL, upstream_id TEXT NOT NULL, downstream_type TEXT NOT NULL,
 downstream_id TEXT NOT NULL, relation TEXT NOT NULL, version TEXT, created_at TEXT NOT NULL,
 UNIQUE(project_id,upstream_type,upstream_id,downstream_type,downstream_id,relation));
CREATE TABLE IF NOT EXISTS supervisor_claims(
 claim_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, claim TEXT NOT NULL, allowed INTEGER NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '[]', reason TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(
 decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, topic TEXT NOT NULL,
 trigger TEXT, recommendation TEXT, options_json TEXT NOT NULL DEFAULT '[]',
 status TEXT NOT NULL DEFAULT 'proposed', choice TEXT, comment TEXT,
 created_at TEXT NOT NULL, resolved_at TEXT);
"""
def now(): return datetime.now(timezone.utc).isoformat()
def jd(v): return json.dumps(v,ensure_ascii=False,sort_keys=True)
class Supervisor:
 def __init__(self,db):
  self.path=Path(db); self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.connect() as c: c.executescript(SCHEMA)
 @contextmanager
 def connect(self):
  c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row
  try: yield c; c.commit()
  except Exception: c.rollback(); raise
  finally: c.close()
 def project_id(self):
  with self.connect() as c:
   rows=c.execute('SELECT project_id FROM projects').fetchall()
  if len(rows)!=1: raise ValueError('expected exactly one base project')
  return rows[0][0]
 def next_id(self,table,col,prefix):
  with self.connect() as c: vals=[r[0] for r in c.execute(f'SELECT {col} FROM {table}').fetchall()]
  nums=[]
  for v in vals:
   if isinstance(v,str) and v.startswith(prefix+'-'):
    try: nums.append(int(v.rsplit('-',1)[1]))
    except ValueError: pass
  return f'{prefix}-{max(nums,default=0)+1:03d}'
 def init_lifecycle(self):
  pid=self.project_id(); ts=now()
  with self.connect() as c:
   for i,phase in enumerate(PHASES):
    rid=f'RUN-{i:02d}'
    c.execute('INSERT OR IGNORE INTO supervisor_phase_runs VALUES(?,?,?,?,?,?,?,?)',(rid,pid,phase,'active' if i==0 else 'planned','{}','{}',ts,None))
 def add_work(self,phase,module,title,objective,priority=50,depends=None,inputs=None,acceptance=None,capability_floor=None,owner_required=False):
  if phase not in PHASES: raise ValueError(phase)
  pid=self.project_id(); wid=self.next_id('supervisor_work_items','work_id','W'); ts=now()
  with self.connect() as c:
   c.execute('INSERT INTO supervisor_work_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
    wid,pid,phase,module,title,objective,priority,'queued',1 if owner_required else 0,None,jd(depends or []),jd(inputs or {}),'{}',jd(acceptance or {}),capability_floor,None,0,ts,ts))
  return wid
 def _deps_complete(self,c,deps):
  for dep in deps:
   r=c.execute('SELECT status FROM supervisor_work_items WHERE work_id=?',(dep,)).fetchone()
   if not r or r[0]!='complete': return False
  return True
 def next_work(self):
  pid=self.project_id()
  with self.connect() as c:
   decision=c.execute("SELECT decision_id FROM decisions WHERE status='proposed' LIMIT 1").fetchone()
   rows=c.execute("SELECT * FROM supervisor_work_items WHERE project_id=? AND status IN ('queued','ready','internal_rework') ORDER BY priority DESC,created_at",(pid,)).fetchall()
   for r in rows:
    d=dict(r); deps=json.loads(d['depends_on_json'])
    if not self._deps_complete(c,deps): continue
    if d['owner_required'] and decision:
     c.execute("UPDATE supervisor_work_items SET status='blocked_decision',decision_id=?,updated_at=? WHERE work_id=?",(decision[0],now(),d['work_id'])); continue
    c.execute("UPDATE supervisor_work_items SET status='running',attempts=attempts+1,updated_at=? WHERE work_id=?",(now(),d['work_id']))
    d['status']='running'; d['depends_on']=deps; return d
  return None
 def complete(self,wid,outputs=None):
  with self.connect() as c:
   if not c.execute('SELECT 1 FROM supervisor_work_items WHERE work_id=?',(wid,)).fetchone(): raise KeyError(wid)
   c.execute("UPDATE supervisor_work_items SET status='complete',outputs_json=?,updated_at=? WHERE work_id=?",(jd(outputs or {}),now(),wid))
 def fail(self,wid,reason,external=False,retry=True):
  st='blocked_external' if external else ('internal_rework' if retry else 'cancelled')
  with self.connect() as c: c.execute('UPDATE supervisor_work_items SET status=?,blocked_reason=?,updated_at=? WHERE work_id=?',(st,reason,now(),wid))
 def register_capability(self,name,status,provider=None,maturity_ceiling=None,metadata=None):
  pid=self.project_id(); cid=self.next_id('supervisor_capabilities','capability_id','CAP'); ts=now()
  with self.connect() as c: c.execute('INSERT INTO supervisor_capabilities VALUES(?,?,?,?,?,?,?,?)',(cid,pid,name,provider,status,maturity_ceiling,jd(metadata or {}),ts))
  return cid
 def add_lineage(self,ut,uid,dt,did,relation='derives',version=None):
  with self.connect() as c: c.execute('INSERT OR IGNORE INTO supervisor_lineage(project_id,upstream_type,upstream_id,downstream_type,downstream_id,relation,version,created_at) VALUES(?,?,?,?,?,?,?,?)',(self.project_id(),ut,uid,dt,did,relation,version,now()))
 def review(self,target_type,target_id,review_type,result,findings=None,reviewer='AI-independent-auditor'):
  rid=self.next_id('supervisor_reviews','review_id','REV')
  with self.connect() as c: c.execute('INSERT INTO supervisor_reviews VALUES(?,?,?,?,?,?,?,?,?)',(rid,self.project_id(),target_type,target_id,review_type,result,jd(findings or []),reviewer,now()))
  return rid
 def status(self):
  with self.connect() as c:
   counts={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM supervisor_work_items GROUP BY status')}
   phases=[dict(r) for r in c.execute('SELECT * FROM supervisor_phase_runs ORDER BY run_id')]
   caps=[dict(r) for r in c.execute('SELECT * FROM supervisor_capabilities ORDER BY checked_at DESC')]
   running=[dict(r) for r in c.execute("SELECT work_id,phase,module,title,status FROM supervisor_work_items WHERE status IN ('running','blocked_decision','blocked_external')")]
  return {'work_counts':counts,'phases':phases,'capabilities':caps,'active_or_blocked':running}
 def _set_status(self,wid,status,decision_id=None):
  with self.connect() as c:
   if decision_id:
    c.execute('UPDATE supervisor_work_items SET status=?,decision_id=?,updated_at=? WHERE work_id=?',(status,decision_id,now(),wid))
   else:
    c.execute('UPDATE supervisor_work_items SET status=?,updated_at=? WHERE work_id=?',(status,now(),wid))
 def _persist_decision(self,wid,pkg):
  pid=self.project_id(); ts=now()
  with self.connect() as c:
   c.execute('INSERT INTO decisions(decision_id,project_id,topic,trigger,recommendation,options_json,status,created_at) VALUES(?,?,?,?,?,?,?,?)',
    (pkg['decision_id'],pid,pkg['decision']['topic'],pkg['decision']['category'],pkg['recommendation'],jd(pkg['options']),'proposed',ts))
 def _register_outputs(self,wid,capability_floor,out):
  try: self.register_capability(capability_floor,'available',provider=out['record'].provider)
  except Exception: pass
  self.add_lineage('work_item',wid,'run',out['record'].run_id,'executed_via')
 def run_supervisor(self,steps=1,adapter_registry=None,router=None,decision_policy=None):
  """驱动监督器执行：直到需要决策或工作耗尽。
  返回每个步骤的结果列表（complete / internal_rework / blocked_external / decision）。
  """
  from aipd_os.logging_utils import get_logger, log_event
  logger=get_logger('aipd.supervisor')
  from aipd_os.execution.decision_policy import build_decision_package, should_ask_decision
  from aipd_os.execution.execution_router import ExecutionRouter
  from aipd_os.execution.runs import RunStore
  from aipd_os.tool_adapters.builtin import build_registry
  if adapter_registry is None: adapter_registry=build_registry()
  if router is None:
   _store=RunStore(str(self.path.parent/'execution_runs.db'))
   router=ExecutionRouter(_store,adapter_registry,get_logger('aipd.router'))
  if decision_policy is None: decision_policy=should_ask_decision
  results=[]
  for _ in range(steps):
   item=self.next_work()
   if item is None:
    log_event(logger,'supervisor_no_work'); break
   wid=item['work_id']
   inputs=json.loads(item['inputs_json'])
   capability_floor=item.get('capability_floor') or inputs.get('capability_floor')
   log_event(logger,'supervisor_step_started',work_id=wid,phase=item.get('phase'),module=item.get('module'),capability_floor=capability_floor)
   if item.get('owner_required') or decision_policy(item,inputs):
    pkg=build_decision_package(item,options=item.get('options') or inputs.get('options'))
    self._persist_decision(wid,pkg); self._set_status(wid,'blocked_decision',pkg['decision_id'])
    log_event(logger,'supervisor_decision_required',work_id=wid,decision_id=pkg['decision_id'])
    results.append({'work_id':wid,'action':'decision','decision':pkg}); continue
   if not capability_floor or adapter_registry.get(capability_floor) is None:
    reason='no capability_floor assigned' if not capability_floor else f'no adapter registered for {capability_floor}'
    self.fail(wid,reason,external=False,retry=True)
    log_event(logger,'supervisor_no_adapter',work_id=wid,reason=reason)
    results.append({'work_id':wid,'action':'internal_rework','reason':reason}); continue
   try:
    out=router.run(wid,capability_floor,inputs,context={'work_id':wid})
    record=out['record']
    if record.status in ('succeeded','fallback'):
     self.complete(wid,outputs=out['result']); self._register_outputs(wid,capability_floor,out)
     log_event(logger,'supervisor_work_complete',work_id=wid,status=record.status,run_id=record.run_id)
     results.append({'work_id':wid,'action':'complete','status':record.status,'record':record.to_dict()})
    elif record.status=='blocked_external':
     self.fail(wid,record.error_message or 'external capability unavailable',external=True,retry=False)
     log_event(logger,'supervisor_work_blocked_external',work_id=wid,run_id=record.run_id)
     results.append({'work_id':wid,'action':'blocked_external','record':record.to_dict()})
    else:
     self.fail(wid,record.error_message or 'execution failed',external=False,retry=True)
     log_event(logger,'supervisor_work_failed',work_id=wid,status=record.status,run_id=record.run_id)
     results.append({'work_id':wid,'action':'internal_rework','status':record.status,'record':record.to_dict()})
   except Exception as exc:
    self.fail(wid,str(exc),external=False,retry=True)
    log_event(logger,'supervisor_work_error',work_id=wid,error=str(exc))
    results.append({'work_id':wid,'action':'internal_rework','error':str(exc)})
  return results

def parser():
 p=argparse.ArgumentParser(); p.add_argument('--db',required=True); sub=p.add_subparsers(dest='cmd',required=True)
 sub.add_parser('init')
 s=sub.add_parser('add-work'); s.add_argument('--phase',required=True); s.add_argument('--module',required=True); s.add_argument('--title',required=True); s.add_argument('--objective',required=True); s.add_argument('--priority',type=int,default=50); s.add_argument('--depends-json',default='[]'); s.add_argument('--inputs-json',default='{}'); s.add_argument('--acceptance-json',default='{}'); s.add_argument('--capability-floor'); s.add_argument('--owner-required',action='store_true')
 sub.add_parser('next')
 s=sub.add_parser('complete'); s.add_argument('--work-id',required=True); s.add_argument('--outputs-json',default='{}')
 s=sub.add_parser('fail'); s.add_argument('--work-id',required=True); s.add_argument('--reason',required=True); s.add_argument('--external',action='store_true'); s.add_argument('--no-retry',action='store_true')
 s=sub.add_parser('register-capability'); s.add_argument('--name',required=True); s.add_argument('--status',required=True); s.add_argument('--provider'); s.add_argument('--maturity-ceiling'); s.add_argument('--metadata-json',default='{}')
 s=sub.add_parser('lineage'); s.add_argument('--upstream-type',required=True); s.add_argument('--upstream-id',required=True); s.add_argument('--downstream-type',required=True); s.add_argument('--downstream-id',required=True); s.add_argument('--relation',default='derives'); s.add_argument('--version')
 s=sub.add_parser('run'); s.add_argument('--steps',type=int,default=1)
 sub.add_parser('status')
 return p

def main():
 a=parser().parse_args(); s=Supervisor(a.db)
 if a.cmd=='init': s.init_lifecycle(); out={'ok':True}
 elif a.cmd=='add-work': out={'work_id':s.add_work(a.phase,a.module,a.title,a.objective,a.priority,json.loads(a.depends_json),json.loads(a.inputs_json),json.loads(a.acceptance_json),a.capability_floor,a.owner_required)}
 elif a.cmd=='next': out={'work':s.next_work()}
 elif a.cmd=='complete': s.complete(a.work_id,json.loads(a.outputs_json)); out={'ok':True}
 elif a.cmd=='fail': s.fail(a.work_id,a.reason,a.external,not a.no_retry); out={'ok':True}
 elif a.cmd=='register-capability': out={'capability_id':s.register_capability(a.name,a.status,a.provider,a.maturity_ceiling,json.loads(a.metadata_json))}
 elif a.cmd=='lineage': s.add_lineage(a.upstream_type,a.upstream_id,a.downstream_type,a.downstream_id,a.relation,a.version); out={'ok':True}
 elif a.cmd=='run': out={'results':s.run_supervisor(a.steps)}
 elif a.cmd=='status': out=s.status()
 print(json.dumps(out,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': sys.exit(main())
