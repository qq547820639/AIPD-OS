#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from PIL import Image


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--input-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--label', default='owner-approved golden reference')
    args=ap.parse_args()
    root=Path(args.input_dir)
    items=[]
    for p in sorted(root.iterdir()):
        if not p.is_file() or p.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}:
            continue
        with Image.open(p) as im:
            items.append({'file':p.name,'width':im.width,'height':im.height,'mode':im.mode,'sha256':sha256(p)})
    result={'label':args.label,'source_dir':str(root.resolve()),'count':len(items),'items':items,
            'status':'golden_reference_registered' if items else 'empty'}
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if items else 2

if __name__=='__main__':
    raise SystemExit(main())
