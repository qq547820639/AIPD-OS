#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FACT_STATUSES = {"V", "S", "C", "E", "A", "P", "T", "R"}
PROJECT_STATUSES = {"active", "awaiting_owner_decision", "blocked_external", "internal_rework", "released", "archived"}

SCHEMA = r"""
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  goal TEXT NOT NULL,
  gate TEXT NOT NULL DEFAULT 'G0',
  status TEXT NOT NULL DEFAULT 'active',
  version TEXT NOT NULL DEFAULT '0.1.0',
  owner_policy TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
  fact_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  unit TEXT,
  tolerance TEXT,
  conditions TEXT,
  status TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5,
  source TEXT,
  version TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(project_id, key, version)
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  identifier TEXT,
  accessed_at TEXT,
  quality TEXT,
  summary TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_evidence (
  fact_id TEXT NOT NULL REFERENCES facts(fact_id) ON DELETE CASCADE,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT 'supports',
  PRIMARY KEY(fact_id, evidence_id, relation)
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  topic TEXT NOT NULL,
  trigger TEXT,
  recommendation TEXT,
  options_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'proposed',
  choice TEXT,
  comment TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS deliverables (
  deliverable_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  path TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  version TEXT,
  gate TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dependencies (
  dependency_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'affects',
  UNIQUE(project_id, source_type, source_id, target_type, target_id, relation)
);
CREATE TABLE IF NOT EXISTS risks (
  risk_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  probability TEXT,
  impact TEXT,
  mitigation TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  owner TEXT NOT NULL DEFAULT 'AI',
  trigger TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
  change_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  action TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  reason TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gates (
  gate_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  gate TEXT NOT NULL,
  result TEXT NOT NULL,
  checks_json TEXT NOT NULL DEFAULT '{}',
  approved_by TEXT NOT NULL DEFAULT 'AI-internal',
  created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class AIPDStore:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_project(self, project_id: str, name: str, goal: str, owner_policy: str = "AI executes; owner reviews decisions only") -> None:
        ts = now()
        with self.connect() as c:
            c.execute("INSERT INTO projects(project_id,name,goal,gate,status,version,owner_policy,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (project_id,name,goal,"G0","active","0.1.0",owner_policy,ts,ts))

    def project(self) -> dict:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        if len(rows) != 1:
            raise ValueError(f"Expected exactly one project in database, found {len(rows)}")
        return dict(rows[0])

    def _next_id(self, table: str, column: str, prefix: str) -> str:
        with self.connect() as c:
            values = [r[0] for r in c.execute(f"SELECT {column} FROM {table}").fetchall()]
        nums=[]
        for value in values:
            if isinstance(value,str) and value.startswith(prefix+'-'):
                try: nums.append(int(value.split('-')[-1]))
                except ValueError:  # noqa: EMPTY_EXCEPT - 跳过非数字后缀 id
                    pass
        return f"{prefix}-{max(nums, default=0)+1:03d}"

    def add_fact(self, key: str, value: Any, status: str, unit: str | None=None, tolerance: str | None=None,
                 conditions: str | None=None, confidence: float=0.5, source: str | None=None, version: str | None=None) -> str:
        if status not in FACT_STATUSES: raise ValueError(f"Invalid fact status: {status}")
        if not 0 <= confidence <= 1: raise ValueError("confidence must be in [0,1]")
        p=self.project(); fact_id=self._next_id('facts','fact_id','F'); ts=now()
        with self.connect() as c:
            c.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (fact_id,p['project_id'],key,_json(value),unit,tolerance,conditions,status,confidence,source,version,ts,ts))
            c.execute("INSERT INTO changes(project_id,object_type,object_id,action,after_json,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                      (p['project_id'],'fact',fact_id,'create',_json({'key':key,'value':value,'status':status}),'add fact',ts))
        return fact_id

    def add_evidence(self, kind: str, title: str, url: str | None=None, identifier: str | None=None,
                     quality: str | None=None, summary: str | None=None, metadata: dict | None=None,
                     accessed_at: str | None=None) -> str:
        p=self.project(); eid=self._next_id('evidence','evidence_id','E'); ts=now()
        with self.connect() as c:
            c.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (eid,p['project_id'],kind,title,url,identifier,accessed_at or ts,quality,summary,_json(metadata or {}),ts))
        return eid

    def link_evidence(self, fact_id: str, evidence_id: str, relation: str='supports') -> None:
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO fact_evidence VALUES(?,?,?)",(fact_id,evidence_id,relation))

    def propose_decision(self, topic: str, recommendation: str, options: list | dict, trigger: str | None=None) -> str:
        p=self.project(); did=self._next_id('decisions','decision_id','D'); ts=now()
        with self.connect() as c:
            c.execute("INSERT INTO decisions(decision_id,project_id,topic,trigger,recommendation,options_json,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (did,p['project_id'],topic,trigger,recommendation,_json(options),'proposed',ts))
            c.execute("UPDATE projects SET status='awaiting_owner_decision',updated_at=? WHERE project_id=?",(ts,p['project_id']))
        return did

    def resolve_decision(self, decision_id: str, choice: str, comment: str | None=None) -> None:
        p=self.project(); ts=now()
        with self.connect() as c:
            row=c.execute("SELECT * FROM decisions WHERE decision_id=?",(decision_id,)).fetchone()
            if not row: raise KeyError(decision_id)
            c.execute("UPDATE decisions SET status='resolved',choice=?,comment=?,resolved_at=? WHERE decision_id=?",(choice,comment,ts,decision_id))
            open_count=c.execute("SELECT COUNT(*) FROM decisions WHERE status='proposed'").fetchone()[0]
            new_status='awaiting_owner_decision' if open_count else 'active'
            c.execute("UPDATE projects SET status=?,updated_at=? WHERE project_id=?",(new_status,ts,p['project_id']))

    def add_deliverable(self, dtype: str, path: str | None=None, status: str='planned', version: str | None=None,
                        gate: str | None=None, metadata: dict | None=None) -> str:
        p=self.project(); did=self._next_id('deliverables','deliverable_id','DEL'); ts=now()
        with self.connect() as c:
            c.execute("INSERT INTO deliverables VALUES(?,?,?,?,?,?,?,?,?)",
                      (did,p['project_id'],dtype,path,status,version,gate,_json(metadata or {}),ts))
        return did

    def add_risk(self, title: str, probability: str | None=None, impact: str | None=None,
                 mitigation: str | None=None, status: str='open', trigger: str | None=None) -> str:
        p=self.project(); rid=self._next_id('risks','risk_id','RISK'); ts=now()
        with self.connect() as c:
            c.execute("INSERT INTO risks VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (rid,p['project_id'],title,probability,impact,mitigation,status,'AI',trigger,ts))
        return rid

    def set_gate(self, gate: str, status: str | None=None, version: str | None=None) -> None:
        if not (len(gate)==2 and gate[0]=='G' and gate[1].isdigit()): raise ValueError('gate must be G0..G9')
        p=self.project(); ts=now()
        with self.connect() as c:
            c.execute("UPDATE projects SET gate=?,status=COALESCE(?,status),version=COALESCE(?,version),updated_at=? WHERE project_id=?",
                      (gate,status,version,ts,p['project_id']))

    def add_dependency(self, source_type: str, source_id: str, target_type: str, target_id: str, relation: str='affects') -> None:
        p=self.project()
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO dependencies(project_id,source_type,source_id,target_type,target_id,relation) VALUES(?,?,?,?,?,?)",
                      (p['project_id'],source_type,source_id,target_type,target_id,relation))

    def impact(self, source_type: str, source_id: str) -> list[dict]:
        with self.connect() as c:
            rows=c.execute("SELECT * FROM dependencies WHERE source_type=? AND source_id=?",(source_type,source_id)).fetchall()
        return [dict(r) for r in rows]

    def rows(self, table: str) -> list[dict]:
        allowed={'facts','evidence','fact_evidence','decisions','deliverables','dependencies','risks','changes','gates'}
        if table not in allowed: raise ValueError(table)
        with self.connect() as c: rows=c.execute(f"SELECT * FROM {table}").fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            for k in list(d):
                if k.endswith('_json') and d[k]:
                    try: d[k[:-5]]=json.loads(d.pop(k))
                    except json.JSONDecodeError:  # noqa: EMPTY_EXCEPT - 遗留字段 JSON 解析失败保留原样
                        pass
                elif k=='value_json':
                    try: d['value']=json.loads(d.pop(k))
                    except json.JSONDecodeError:  # noqa: EMPTY_EXCEPT - 遗留字段 JSON 解析失败保留原样
                        pass
            out.append(d)
        return out

    def summary(self) -> dict:
        p=self.project()
        with self.connect() as c:
            fact_counts={r['status']:r['n'] for r in c.execute("SELECT status,COUNT(*) n FROM facts GROUP BY status")}
            counts={t:c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ['facts','evidence','decisions','deliverables','risks']}
            open_decisions=c.execute("SELECT decision_id,topic,recommendation FROM decisions WHERE status='proposed'").fetchall()
            top_risks=c.execute("SELECT risk_id,title,probability,impact FROM risks WHERE status='open' ORDER BY updated_at DESC LIMIT 5").fetchall()
        return {'project':p,'counts':counts,'fact_statuses':fact_counts,'open_decisions':[dict(r) for r in open_decisions],'top_open_risks':[dict(r) for r in top_risks]}

    def validate(self) -> list[str]:
        errors=[]
        try: p=self.project()
        except Exception as e: return [str(e)]
        if p['status'] not in PROJECT_STATUSES: errors.append(f"invalid project status {p['status']}")
        if not (len(p['gate'])==2 and p['gate'][0]=='G' and p['gate'][1].isdigit()): errors.append(f"invalid gate {p['gate']}")
        for f in self.rows('facts'):
            if f['status'] not in FACT_STATUSES: errors.append(f"{f['fact_id']} invalid status")
            if not 0 <= f['confidence'] <= 1: errors.append(f"{f['fact_id']} invalid confidence")
        if p['status']=='awaiting_owner_decision' and not any(d['status']=='proposed' for d in self.rows('decisions')):
            errors.append('project awaits decision but no proposed decision exists')
        return errors

    def export(self) -> dict:
        return {
            'project': self.project(),
            'facts': self.rows('facts'),
            'evidence': self.rows('evidence'),
            'fact_evidence': self.rows('fact_evidence'),
            'decisions': self.rows('decisions'),
            'deliverables': self.rows('deliverables'),
            'risks': self.rows('risks'),
            'dependencies': self.rows('dependencies'),
            'changes': self.rows('changes'),
            'gates': self.rows('gates'),
        }
