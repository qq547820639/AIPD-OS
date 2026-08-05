#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from PIL import Image
import numpy as np


def entropy(gray: np.ndarray) -> float:
    hist=np.bincount(gray.ravel(), minlength=256).astype(float)
    hist/=hist.sum()
    nz=hist[hist>0]
    return float(-(nz*np.log2(nz)).sum())


def edge_density(gray: np.ndarray) -> float:
    # dependency-free Sobel-like gradient proxy
    a=gray.astype(float)
    gx=np.abs(np.diff(a,axis=1))
    gy=np.abs(np.diff(a,axis=0))
    return float(((gx>25).mean()+(gy>25).mean())/2)


def ahash(im: Image.Image, size: int=16) -> str:
    g=np.asarray(im.convert('L').resize((size,size)))
    return ''.join('1' if x>=g.mean() else '0' for x in g.ravel())


def hamming(a: str,b: str) -> int:
    return sum(x!=y for x,y in zip(a,b))


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--pages-dir',required=True)
    ap.add_argument('--contract',required=True)
    ap.add_argument('--json-out')
    args=ap.parse_args()
    contract=json.loads(Path(args.contract).read_text(encoding='utf-8'))
    root=Path(args.pages_dir)
    pages=sorted([p for p in root.iterdir() if p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'}])
    rows=[]; hashes=[]
    for p in pages:
        with Image.open(p) as im0:
            im=im0.convert('RGB')
            arr=np.asarray(im)
            gray=np.asarray(im.convert('L'))
            rows.append({
                'file':p.name,'width':im.width,'height':im.height,
                'white_ratio':float(np.mean(np.all(arr>245,axis=2))),
                'entropy':entropy(gray),'edge_density':edge_density(gray),
                'hash':ahash(im)
            })
            hashes.append(rows[-1]['hash'])
    duplicates=[]
    for i in range(len(hashes)):
        for j in range(i+1,len(hashes)):
            if hamming(hashes[i],hashes[j])<=contract.get('duplicate_hash_distance_max',4):
                duplicates.append([rows[i]['file'],rows[j]['file']])
    expected=contract.get('expected_page_count')
    min_w=contract.get('min_width',0); min_h=contract.get('min_height',0)
    checks={
        'pages_present':len(rows)>0,
        'page_count': expected is None or len(rows)==expected,
        'dimensions': all(r['width']>=min_w and r['height']>=min_h for r in rows),
        'portrait': all(r['height']>r['width'] for r in rows),
        'no_duplicates':len(duplicates)==0,
        'not_extremely_blank':all(r['white_ratio']<=contract.get('max_white_ratio',0.92) for r in rows),
        'minimum_visual_information':all(r['entropy']>=contract.get('min_entropy',1.5) for r in rows),
    }
    result={
        'pages_dir':str(root.resolve()),'page_count':len(rows),'checks':checks,
        'deterministic_preflight_passed':all(checks.values()),
        'duplicates':duplicates,'pages':rows,
        'warning':'Deterministic preflight is necessary but not sufficient. Independent visual review against a golden reference is mandatory.'
    }
    text=json.dumps(result,ensure_ascii=False,indent=2)
    print(text)
    if args.json_out: Path(args.json_out).write_text(text+'\n',encoding='utf-8')
    return 0 if result['deterministic_preflight_passed'] else 3

if __name__=='__main__':
    raise SystemExit(main())
