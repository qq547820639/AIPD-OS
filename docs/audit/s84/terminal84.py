"""给第 84 片取证文档补一节「六、终局读数」——所有数字一律现读，不手抄。

跑法：先把收口的四件事做完（绑定、发布门、收尾验签），再跑本文件。
本文件自己只做一件额外的事：**拿真仓库现场演示一次拒写**（见 `_refusal_demo`），
因为它不需要改树上的任何字节——闸排在写盘之前，拒了就是一个字节都不写。

闸门（任一不过就整节不写）：
① 绑进证据的那份报告自记的清单指纹 == 磁盘 `SOURCE_MANIFEST.json` 的内容规范摘要；
② 干净签出那一跑 0 failed 且 exitcode==0；
③ 发布门 `release_ready=True` 且逐项全过；
④ 收尾验签那一行判决为「全部判据绿」；
⑤ 现场拒写演示：坏报告退 2、输出点名指纹、且目标目录里**一个文件都没有**；
⑥ 写完后 §一/§四/§六/§七/§八 五个标题各存在一次且顺序正确。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

R = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
S = R / "docs/audit/s84"
OUT = Path("/Volumes/Extra/CodeProj/AI全链路自研/.s84-refusal")
SRATCH = Path("/Volumes/Extra/CodeProj/AI全链路自研/.s84-scratch")
DOC = R / "docs/audit/BIND_PREFLIGHT_F-BIND-PREFLIGHT_2026-09-28.md"
PY = str(R / ".venv/bin/python")
sys.path.insert(0, str(R / "scripts"))
import release_fingerprint as rf  # noqa: E402


def sh(args):
    p = subprocess.run(args, cwd=str(R), capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def _refusal_demo(manifest_fp: str, report: dict) -> tuple[str, str, int, list[str]]:
    """拿真仓库 + 一份"指纹不同源"的报告，现场演示一次拒写。返回 (rec, 消息, rc, 落盘清单)。"""
    bad = dict(report)
    bad["source_manifest_fingerprint"] = "0" * 64      # 与磁盘清单必然不同源
    # 故意**不预先创建** OUT：闸之后才有 mkdir，所以被拒时这个目录应当根本不存在。
    if OUT.exists():
        shutil.rmtree(OUT)
    rep = SRATCH / "bad-report.json"
    SRATCH.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps(bad), encoding="utf-8")
    p = subprocess.run([PY, "scripts/release_evidence.py", "--repo", ".", "--out", str(OUT),
                        "--version", "5.6.0", "--source-commit", str(report["source_commit"]),
                        "--test-report", str(rep)],
                       cwd=str(R), capture_output=True, text=True)
    left = sorted(x.name for x in OUT.iterdir()) if OUT.exists() else []
    created = OUT.exists()
    if created:
        shutil.rmtree(OUT)
    return (str(bad["source_manifest_fingerprint"]), (p.stdout + p.stderr).strip(),
            p.returncode, left, created)


def main() -> int:
    bound = json.loads((R / "docs/audit/pytest-report-v5.6.0.json").read_text(encoding="utf-8"))
    disk_fp, err = rf.fingerprint_from_file(R / "SOURCE_MANIFEST.json")
    rec_fp = str(bound.get("source_manifest_fingerprint") or "")
    assert not err and rec_fp and rec_fp == disk_fp, f"①：报告 {rec_fp[:12]} vs 磁盘 {disk_fp[:12]} {err}"

    summ = bound["summary"]
    # 同 closeout84.sh：`failed` 键在 0 failed 时缺席，缺席要按 0 读（与生产侧同口径推导）
    n_failed = summ["failed"] if "failed" in summ else max(
        summ["total"] - summ["passed"] - summ.get("skipped", 0), 0)
    assert n_failed == 0 and bound.get("exitcode") == 0, f"②：{summ}"
    dur = round(float(bound.get("duration", 0.0)), 1)

    gate_p = S / "gate.json"
    assert gate_p.is_file(), f"缺 {gate_p}：先跑发布门并带 --json 输出到那里"
    gd = json.loads(gate_p.read_text(encoding="utf-8"))
    checks = gd["checks"]
    bad_items = [c["name"] for c in checks if not c.get("passed")]
    assert gd.get("release_ready") is True and not bad_items, f"③：{bad_items}"

    cv_p = S / "closeout.json"
    assert cv_p.is_file(), f"缺 {cv_p}：先跑收尾验签并带 --json"
    cv = json.loads(cv_p.read_text(encoding="utf-8"))
    assert not cv.get("violations"), f"④：{[v['check'] for v in cv['violations']]}"
    assert not cv.get("problems"), f"④：前提塌 {list(cv['problems'])}"
    n_checks = len(cv["checks"])

    rec, msg, rc, left, created = _refusal_demo(disk_fp, bound)
    assert rc == 2 and "!= 即将写出的这份清单" in msg, f"⑤：rc={rc} {msg[:160]}"
    assert left == [] and created is False, f"⑤：被拒时不该有任何落盘动作，实得 created={created} left={left}"

    log = (S / "battery84.log").read_text(encoding="utf-8")
    tally = re.search(r"合计 KILLED\+CRASH-KILL (\d+) / (\d+)", log)
    assert tally, "电池汇总行读不到"

    head = sh(["git", "rev-parse", "HEAD"])
    anchor = sh(["git", "rev-parse", "v5.6.0^{commit}"])
    bind_commit = sh(["git", "log", "--format=%h", "-1", "--", "PROVENANCE.json"])
    assert re.fullmatch(r"[0-9a-f]{7}", bind_commit or ""), f"绑定提交号取数失败：{bind_commit!r}"
    n_files = len(json.loads((R / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))["files"])

    SEC = f"""## 六、终局读数（绑定那一跑，全部现读）

| 格 | 读数 |
| --- | --- |
| 被认证提交 | `{anchor[:12]}`（tag `v5.6.0`，本轮不重锚） |
| 收口 HEAD | `{head[:12]}` |
| 绑定提交 | `{bind_commit}` |
| 清单分母 | `SOURCE_MANIFEST.json` {n_files} 个文件（`docs/audit/` 整体排除 ⇒ 0 条） |
| 报告自记清单指纹 | `{rec_fp[:12]}` |
| 磁盘清单内容摘要 | `{disk_fp[:12]}` —— **逐位相等**（这道闸自己放行时也是这个判据） |
| 干净签出那一跑 | {summ['passed']} passed / {summ.get('skipped', 0)} skipped / {n_failed} failed，{dur} s，`exitcode={bound['exitcode']}` |
| 发布门 | `release_ready=True`，{len(checks)} 项全过，判红 0 项 |
| 收尾验签 | {n_checks} 格全绿（判红 0、前提塌 0） |
| 变异电池 | 整支八臂 `KILLED {tally.group(1)}/{tally.group(2)}`（W5 是真 BAD-ANCHOR：锚点抄着本轮被改掉的 print 文案）；改锚后 `--only W5` 复算 `1/1 KILLED`。三份日志都入库：`battery84.log` / `battery84.w5.log` / `battery84.run1.log`（更早那次的假 BAD-ANCHOR） |

**现场拒写演示（不是合成夹具，用的是真仓库的清单与真报告的副本）**：
把绑定那份报告的 `source_manifest_fingerprint` 换成 `{'0'*12}…`（{n_files} 格清单的内容摘要
实际是 `{disk_fp[:12]}`），再拿它去跑带 `--test-report` 的绑定：

```
$ python scripts/release_evidence.py --repo . --out {OUT.name} \\
      --version 5.6.0 --source-commit {anchor[:12]}… --test-report bad-report.json
{msg.splitlines()[0]}
退出码 = {rc}；输出目录是否被创建 = {created}（应为 False）；里面剩下的文件 = {left}（应为 []）
```

三条只能在这一节才说得清的形状：

1. **"拒写不半写"是可以用退码之外的方式看的**：`left == []` 这一格比 rc 强——
   rc=2 只说明被拒，不说明拒在哪一步之前。合成用例（`tests/test_release_evidence_preflight.py`）
   判的是同一件事的 tmp 版，这一格判的是真仓库版。
2. **闸改变的是收口的失败形状**：它把"事后由 C11 读成红"前移成"当场拒"。
   上一片的靶子见 §二③（`424e343708fd` vs `74b031491f1a`）。
3. **本轮真实烧掉的那一跑**：README 的一个计数句在启动干净全量之后才被改（20 → 21），
   于是那一跑必须作废重跑——这正是第 84 片这条闸在收口流程里的日常形状：
   hashed 面的文字必须赶在启动那一跑之前定稿。
"""

    t = DOC.read_text(encoding="utf-8")
    assert "## 六、终局读数" not in t, "已经补过了（幂等闸）"
    anchor_head = "## 七、复算入口"
    assert t.count(anchor_head) == 1, t.count(anchor_head)
    DOC.write_text(t.replace(anchor_head, SEC + anchor_head, 1), encoding="utf-8")

    order = [DOC.read_text(encoding="utf-8").index(x) for x in
             ("## 一、入口与理由", "## 四、电池", "## 六、终局读数", "## 七、复算入口", "## 八、遗留")]
    assert order == sorted(order), f"章节顺序被写坏了：{order}"
    for x in ("## 六、终局读数", "## 七、复算入口"):
        assert DOC.read_text(encoding="utf-8").count(x) == 1, x
    print(f"已补 §六：{head[:7]} / 报告 {summ['passed']} passed / 电池 {tally.group(1)}/{tally.group(2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
