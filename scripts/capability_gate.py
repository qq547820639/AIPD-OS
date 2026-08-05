#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
ORDER=['C0','C1','C2','C3','C4','C5','C6','C7']
def allowed(capability,target):
 if capability not in ORDER or target not in ORDER: return False
 return ORDER.index(capability)>=ORDER.index(target)
def main():
 p=argparse.ArgumentParser(); p.add_argument('--ceiling',required=True); p.add_argument('--target',required=True); a=p.parse_args()
 ok=allowed(a.ceiling,a.target); out={'ok':ok,'ceiling':a.ceiling,'target':a.target,'required_action':'proceed' if ok else 'switch_tool_or_lower_claim'}
 print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if ok else 1
if __name__=='__main__': sys.exit(main())
