#!/usr/bin/env python3
"""第 87 片终局读数：把"绑定那一跑"的五处证据一次性现读出来，供取证文档 §九 粘贴。

设计约束（都是本仓记过的形状）：
- 每一步的数都从**盘上的证件**读，不从我记忆的数抄；缺件就打印缺件而不是猜一个；
- `failed` 在 pytest-json-report 里 0 时是**缺席**而不是 0 ⇒ 按生产侧同口径推导；
- 发布门的判决项键名是 `check`（不是 `name`），读错键会得到空列表并与"全过"同形；
- 收尾验签的 `ok` 与逐项 `checks` 都要报：只看总布尔会把"只是越界"读成"真违规"。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]     # s87 → audit → docs → 仓库根
S = REPO / "docs" / "audit" / "s87"


def load(p: Path) -> object | None:
    if not p.is_file():
        print(f"  （缺件：{p.relative_to(REPO)}）")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  （解析失败：{p.relative_to(REPO)}：{exc}）")
        return None


def main() -> int:
    missing = 0
    print("=" * 62)
    print("第 87 片终局读数（全部现读，不抄记忆）")
    print("=" * 62)

    rep = load(REPO / "docs" / "audit" / "pytest-report-v5.6.0.json")
    if rep is None:
        missing += 1
    else:
        s = rep["summary"]
        failed = s["failed"] if "failed" in s else max(
            s["total"] - s["passed"] - s.get("skipped", 0), 0)
        print(f"1) 绑定那跑的报告：passed {s['passed']} / skipped {s.get('skipped', 0)} / "
              f"failed {failed}（键缺席⇒推导）/ total {s['total']} / collected {s.get('collected')} / "
              f"{round(rep['duration'], 1)}s / exitcode {rep.get('exitcode')} / "
              f"root {rep.get('root')}")
        print(f"   锚点 {str(rep.get('source_commit'))[:12]} / 清单指纹 "
              f"{str(rep.get('source_manifest_fingerprint'))[:12]} / "
              f"tests 名单 {len(rep.get('tests', []))} 条")

    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "v5.6.0^{commit}"],
                         capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"2) tag v5.6.0 = {sha[:12]}；当前 HEAD = {head}")

    prov = load(REPO / "PROVENANCE.json")
    if prov is None:
        missing += 1
    else:
        tr = prov.get("test_report", {})
        print(f"3) PROVENANCE：source_commit {str(prov.get('source_commit'))[:12]} / "
              f"test_report present={tr.get('present')} parsed={tr.get('parsed')} "
              f"{tr.get('passed')}p/{tr.get('failed')}f/{tr.get('total')}t / "
              f"指纹 {str(tr.get('source_manifest_fingerprint'))[:12]}")

    # 两代证件都在库里（第一版是作废的那次），所以必须逐份点名报，
    # 绝不能只报其中一份还装作"当前状态"——那正是本件自己刚犯过的错。
    for label, names in (("4) 发布门", ("gate.json", "gate-rerun.json")),
                         ("5) 收尾验签", ("closeout.json", "closeout-final.json"))):
        for n in names:
            g = load(S / n)
            if g is None:
                continue
            if isinstance(g.get("checks"), list):      # 发布门：checks 是列表，项键叫 check
                bad = [c["check"] for c in g["checks"] if not c.get("passed")]
                print(f"{label} [{n}] release_ready={g.get('release_ready')} / "
                      f"{len(g['checks'])} 项 / 未过：{bad or '无'}")
            else:                  # 验签形状：checks 是字典，另有 readings
                chk = g.get("checks", {})
                red = [k for k, v in chk.items() if not v.get("ok")]
                r = g.get("readings", {})
                print(f"{label} [{n}] ok={g.get('ok')} / {len(chk)} 档 / "
                      f"红：{red or '无'} / 报告 {r.get('report_entries')} 条 / "
                      f"终态 {r.get('outcome_hist')} / HEAD {str(r.get('worktree_head'))[:10]}")
    print("   （同名两代时，判红的那代不覆盖：先看哪代是绿的，再认它对应的运行）")

    try:
        out = subprocess.run([sys.executable,
                              str(REPO / "scripts" / "doc_command_census.py")],
                             capture_output=True, text=True, cwd=REPO)
    except OSError as exc:                      # 解释器或尺子本身不在 ⇒ 是"没读到"，不是"读到 0"
        print(f"6) 面 ⑤ 现读：读不出（{exc}）⇒ 这一格没有读数")
        missing += 1
        out = None
    if out is not None:
        face = [ln for ln in out.stdout.splitlines() if ln.startswith("判红面 ⑤")]
        tail = [ln for ln in out.stdout.splitlines() if ln.startswith("现状面缺陷")]
        print(f"6) 面 ⑤ 现读（rc={out.returncode}）："
              f"{(face[0] if face else '（没读到那一行）')}")
        if not face:
            missing += 1
        print(f"   {(tail[0] if tail else '（没读到判决行）')}")
        if not tail:
            missing += 1

    worktrees = subprocess.run(["git", "-C", str(REPO), "worktree", "list"],
                               capture_output=True, text=True).stdout.strip().splitlines()
    print(f"7) worktree 登记 {len(worktrees)} 行")
    if missing:
        print(f"缺件 {missing} 处 ⇒ 这些格子还没有读数，别当作 0")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
