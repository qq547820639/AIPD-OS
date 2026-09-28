#!/usr/bin/env python3
"""第 93 片动手前先量：闭包内每个包的**许可证正文**在哪、断言认不认得出、哪些只是提及。

判据不在这里复刻——正文检测全部调 `scripts/dependency_license_gate.py` 自己的
`detect_body` / `bodies_of` / `package_license`（复刻一份就等于量具改了这里还在报旧账）。
复算入口：`python docs/audit/s93/probe93_license_bodies.py`
（从任意目录跑都行，路径按本文件位置推）。

三问（答案直接决定判据形状，取证文档 §一 引的就是这里的读数）：
  1. 正文落在哪：PEP 639 的 `X.dist-info/licenses/**`、老 setuptools 的 `X.dist-info/LICENSE`，
     还是只在包树里（casadi 那种只有 vendored 第三方许可证的）？
  2. 一个包**多份**正文（cryptography 三份、packaging 三份）时，断言取并集还是取第一份？
  3. 只看文件头部（前 8 个非空行）能认出多少个？放宽到全文又会多认出什么——
     多出来的那批就是**误报候选**（实测 `typing-extensions` 的 PSF 正文提到 GPL、
     `numpy` 的正文里 quoted 了 GPL 全文）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]        # docs/audit/s93/ → 仓库根
sys.path.insert(0, str(ROOT / "scripts"))
import dependency_license_gate as dlg  # noqa: E402


def main() -> int:
    idx = dlg.installed_index()
    bodies = dlg.installed_bodies()
    roots = dlg.read_declared_roots((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    _reach, seen, _sk = dlg.closure(roots, idx)
    installed = [n for n in sorted(seen) if n in idx]

    print(f"闭包 {len(seen)} 个名字，其中本机已装 {len(installed)} 个；"
          f"dist-info 正文文件共 {sum(len(bodies.get(n, [])) for n in installed)} 个")
    miss = [n for n in installed if not bodies.get(n)]
    unrec = [n for n in installed if bodies.get(n)
             and not {f for _p, t in bodies[n] for f in dlg.detect_body(t)[0]}]
    print(f"没有正文 {len(miss)}：{miss}")
    print(f"有正文但头部认不出 {len(unrec)}：{unrec}")

    print("\n--- 逐包：档位 / 元数据 id / 断言 / 提及（正文文件数）---")
    for name in installed:
        rank, _why, ids, _raw, _c = dlg.package_license(idx[name])
        asserted: set[str] = set()
        mentioned: set[str] = set()
        for _p, t in bodies.get(name, []):
            a, m = dlg.detect_body(t)
            asserted |= set(a)
            mentioned |= set(m)
        print(f"{name:28} {rank:16} {','.join(ids) or '(无)':24} "
              f"断言={sorted(asserted) or '(无)'} 提及={sorted(mentioned) or '-'} "
              f"文件={len(bodies.get(name, []))}")

    print("\n--- 包树里的许可证文件（vendored，必须**不**算它自己的正文）---")
    import importlib.metadata as md
    tree_re = re.compile(r"(LICENSE|LICEN[CS]E[-.\w]*|COPYING[-.\w]*)$", re.I)
    for d in sorted(md.distributions(), key=lambda x: (x.metadata.get("Name") or "").lower()):
        name = dlg._canon(d.metadata.get("Name") or "")
        if name not in installed:
            continue
        outs = [f.as_posix() for f in (d.files or [])
                if tree_re.search(f.as_posix()) and ".dist-info" not in f.as_posix()]
        if outs:
            print(f"{name:28} {len(outs)} 个，例：{outs[:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
