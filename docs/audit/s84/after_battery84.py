"""等电池退出并做三道到货检验，然后把读数交给主线。不写任何文件、不做任何 git 动作。

守卫用电池**自己**记在日志里的基线 sha，而不是我以为的内容——残留变异是这类电池
最真实的自伤面（一臂泄漏会让后续所有臂都报"还原失败"）。
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

R = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
LOG = R / "docs/audit/s84/battery84.log"
PID = sys.argv[1] if len(sys.argv) > 1 else ""


def sha(p: Path) -> str:
    out = subprocess.run(["shasum", "-a", "256", str(p)], cwd=str(R),
                         capture_output=True, text=True).stdout
    return out.split()[0] if out.split() else ""


def main() -> int:
    if PID:
        waited = 0
        while subprocess.run(["kill", "-0", PID], capture_output=True).returncode == 0:
            time.sleep(20)
            waited += 20
            if waited % 300 == 0:
                print(f"…已等 {waited}s", flush=True)
        print(f"battery 进程退出（等待 {waited}s）", flush=True)

    log = LOG.read_text(encoding="utf-8") if LOG.is_file() else ""
    problems = []

    # ① 汇总行必须在
    m = re.search(r"合计 KILLED\+CRASH-KILL (\d+) / (\d+)", log)
    if not m:
        problems.append("日志没有汇总行（电池可能没跑完；日志块缓冲，中途读会是 0 字节）")
    tail = log.split("其余按判决分类：")[-1].strip().splitlines()[0] if log else ""

    # ② 残留：两个靶文件必须回到电池自报的基线 sha
    base = dict(re.findall(r"基线 (\S+\.py) sha=([0-9a-f]{12})", log))
    if len(base) != 2:
        problems.append(f"日志里读不到两条基线 sha（实得 {base}）")
    for name, want in base.items():
        got = sha(R / "scripts" / name)
        if not got.startswith(want):
            problems.append(f"{name} 残留变异：基线 {want} 现在 {got[:12]}")

    # ③ 变异串不得留在树上（逐臂的注入体形状）
    for f in ("release_evidence.py", "closeout_verifier.py"):
        t = (R / "scripts" / f).read_text(encoding="utf-8")
        for needle in ("if False:", "hashlib.sha256(json.dumps(source_doc"):
            if needle in t:
                problems.append(f"scripts/{f} 仍有注入痕迹 {needle!r}")

    print(f"电池读数：{m.group(0) if m else '读不到'}；其余判决：{tail or '读不到'}")
    print("基线 sha 对账：" + (", ".join(f"{k}={v}" for k, v in sorted(base.items())) or "无"))
    bad_arms = re.findall(r"^\[(?!KILLED)([A-Z-]+)\s*\] (\S+)", log, re.M)
    print(f"非 KILLED 臂：{bad_arms or '无'}")
    if problems:
        print("GUARD FAILED:")
        for p in problems:
            print("  -", p)
        return 1
    print("GUARDS OK：无残留，可以进入提交/重锚/全量")
    return 0


if __name__ == "__main__":
    sys.exit(main())
