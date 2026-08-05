#!/usr/bin/env python3
"""Reference MCP server for persistent AIPD state.

Run after installing requirements. Configure AIPD_DB_DIR to a persistent volume.
This file is a deployable skeleton; authentication, tenant isolation, backups and
network exposure must be added for production use.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

SKILL_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL_ROOT/'scripts'))
from aipd_store import AIPDStore
from mcp.server.fastmcp import FastMCP

mcp=FastMCP('aipd-state')
BASE=Path(os.environ.get('AIPD_DB_DIR', str(Path.home()/'.aipd-projects')))
BASE.mkdir(parents=True,exist_ok=True)

def store(project_id: str) -> AIPDStore:
 safe=''.join(c for c in project_id if c.isalnum() or c in '-_')
 if not safe or safe != project_id: raise ValueError('invalid project_id')
 return AIPDStore(BASE/f'{safe}.sqlite')

@mcp.tool()
def init_project(project_id: str, name: str, goal: str) -> str:
 s=store(project_id); s.init_project(project_id,name,goal); return json.dumps(s.summary(),ensure_ascii=False)

@mcp.tool()
def project_summary(project_id: str) -> str:
 return json.dumps(store(project_id).summary(),ensure_ascii=False)

@mcp.tool()
def add_fact(project_id: str, key: str, value_json: str, status: str, unit: str = '', source: str = '', confidence: float = 0.5) -> str:
 value=json.loads(value_json); fid=store(project_id).add_fact(key,value,status,unit or None,confidence=confidence,source=source or None); return fid

@mcp.tool()
def propose_decision(project_id: str, topic: str, recommendation: str, options_json: str, trigger: str = '') -> str:
 return store(project_id).propose_decision(topic,recommendation,json.loads(options_json),trigger or None)

@mcp.tool()
def resolve_decision(project_id: str, decision_id: str, choice: str, comment: str = '') -> str:
 store(project_id).resolve_decision(decision_id,choice,comment or None); return 'ok'

@mcp.tool()
def export_checkpoint(project_id: str) -> str:
 return json.dumps(store(project_id).export(),ensure_ascii=False)

if __name__=='__main__': mcp.run()
