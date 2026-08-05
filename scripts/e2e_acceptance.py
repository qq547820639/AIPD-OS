#!/usr/bin/env python3
"""Compatibility wrapper. AIPD 2.0 no longer treats artifact existence as full closure."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--project-root',required=True); ap.add_argument('--json-out'); ap.add_argument('--require-full',action='store_true')
 a=ap.parse_args(); script=Path(__file__).with_name('outcome_acceptance.py')
 cmd=[sys.executable,str(script),'--project-root',a.project_root,'--require','production' if a.require_full else 'communication']
 if a.json_out: cmd += ['--json-out',a.json_out]
 return subprocess.call(cmd)
if __name__=='__main__': raise SystemExit(main())
