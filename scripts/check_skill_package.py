#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, re, sys
from pathlib import Path

MAX_ZIP=50*1024*1024; MAX_FILE=25*1024*1024; MAX_COUNT=500

def main():
 p=argparse.ArgumentParser(); p.add_argument('root',nargs='?',default=str(Path(__file__).resolve().parents[1])); a=p.parse_args(); root=Path(a.root)
 errors=[]; files=[x for x in root.rglob('*') if x.is_file()]
 skills=[x for x in files if x.name.lower()=='skill.md']
 if len(skills)!=1: errors.append(f'exactly one SKILL.md required, found {len(skills)}')
 else:
  text=skills[0].read_text(encoding='utf-8')
  m=re.match(r'^---\s*\n(.*?)\n---\s*\n',text,re.S)
  if not m: errors.append('SKILL.md missing YAML front matter')
  else:
   fm=m.group(1)
   if not re.search(r'^name:\s*\S+',fm,re.M): errors.append('front matter missing name')
   if not re.search(r'^description:\s*.+',fm,re.M): errors.append('front matter missing description')
 if len(files)>MAX_COUNT: errors.append(f'too many files: {len(files)}')
 for f in files:
  if f.stat().st_size>MAX_FILE: errors.append(f'file too large: {f}')
  if f.suffix.lower() in {'.ttf','.otf','.woff','.woff2'}: errors.append(f'font file must not be distributed: {f}')
  if f.suffix=='.py':
   try: ast.parse(f.read_text(encoding='utf-8'),filename=str(f))
   except Exception as e: errors.append(f'python parse error {f}: {e}')
 print(f'files={len(files)} size={sum(x.stat().st_size for x in files)} bytes')
 if errors:
  print('\n'.join('ERROR: '+e for e in errors)); return 1
 print('OK: package structure and Python syntax checks passed'); return 0
if __name__=='__main__': sys.exit(main())
