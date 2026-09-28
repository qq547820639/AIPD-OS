#!/usr/bin/env python3
"""生成/刷新《CI 面消费表》草案，并保证键与 ci.yml 里的命令**逐字同一来源**。

为什么不手写那 32 条命令：手写就是"复制一份清单"，CI 改一个参数就会漂成
「CI面无人守 + 消费表该撤」两笔红（这正是本尺自己要抓的病）。
所以键一律由 `ci_surface_census.ci_commands()` 现读，分类只按**子串**给，
任何一条命令没被规则接住就**整批不落盘**并点名——宁可停下来，不许留 TODO 落盘。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]          # docs/audit/s91/ -> 仓库根
sys.path.insert(0, str(REPO / "scripts"))
import ci_surface_census as csc  # noqa: E402

ROOT = REPO

SUITE = "本地全量那一跑是无标记的超集（实测 collected 2726，integration 21 条都在名单里）；" \
        "谁跑遍整棵树由 `closeout_verifier` 的 `roster_covers_tree` 那一格证"
ENV = "安装/解包步骤：要联网装包或往 `/usr/local/bin` 写文件（共享状态，不属自决范围）。" \
      "它不判任何东西，红只可能是网络或镜像"
NOASSERT = "命令本身没有可失败的断言（退出码恒 0，只把结果打印出来）⇒ " \
           "把它当门禁是假承诺；本机也未装该工具"

# (子串, kind, consumers, why)。**首条命中即取胜**：CI 里的命令会同时含多个子串
# （`pip install pip-licenses` 既像"装包"又像"那条只列不判的命令"），
# 所以次序就是判据的一部分——具体的排在泛化的前面。
# 命中 0 条 ⇒ 整批不落盘（这条闸门本轮真的拦下过一次：`python -c "import cadquery…"`
# 一开始没规则接它）。命中哪条规则会写进册子的 `matched_rule` 列，供下一轮复核。
BUILD_WHY = (
    "会往 `dist/` 落产物，而收口链硬要求工作树干净（`worktree_clean` 无豁免路径）；"
    "打包一致性由 `tests/test_packaging.py` 在本地判")
GITLEAKS_WHY = (
    "要 gitleaks 二进制（本机实测 `which gitleaks` 无）且它扫的是提交历史，"
    "收口链跑在 detached worktree 上，历史面不在这一格里")

RULES: list[tuple[str, str, list[str], str]] = [
    ("pip-licenses", "ci-only", [], NOASSERT),
    ("-m pytest", "consumed", ["scripts/closeout_verifier.py"], SUITE),
    ("ruff check", "consumed", ["tests/test_ci_face_gates.py"],
     "CI 的 lint job 第一条；第 90 片之前本地一道都不读它，于是一条 E501 活了六轮"),
    ("mypy", "consumed", ["tests/test_ci_face_gates.py"],
     "同一格。`ci.yml:130` 那句「本地硬基线 ruff 0 / mypy 0」在第 91 片现读是 24 个错误/20 个文件"),
    ("aipd_os.scripts.schema_check", "consumed", ["tests/test_ci_face_gates.py"], ""),
    ("import cadquery", "consumed", ["tests/test_cad_golden_loop.py"],
     "内核在场性由那一条用例自己 import 并判；本机实测 cadquery 可导入"),
    ("audit_repo.py", "consumed", ["tests/test_audit_repo.py"],
     "同一份判据由常驻用例在进程内跑（`--json-out` 那一份是产物落盘，不是另一条判据）"),
    ("capability_matrix.py", "consumed", ["tests/test_capability_matrix.py"],
     "矩阵与登记表的一致性由那两条常驻用例核"),
    ("skill_quality_audit.py", "consumed", ["tests/test_skill_command_surface.py"], ""),
    ("audit_dependency_ack.py", "consumed", ["scripts/production_release_gate.py"],
     "发布门的 `no_unacknowledged_cve` 那一格消费同一套 CVE 台账"),
    ("python -m build", "ci-only", [], BUILD_WHY),
    ("pip install", "ci-only", [], ENV),
    ("curl ", "ci-only", [], ENV),
    ("tar -xzf", "ci-only", [], ENV),
    ("gitleaks detect", "ci-only", [], GITLEAKS_WHY),
]

def classify(cmd: str) -> tuple[str, list[str], str, str] | None:
    for sub, kind, cons, why in RULES:
        if sub in cmd:
            return kind, cons, why, sub
    return None


def main() -> int:
    cmds, problems = csc.ci_commands(ROOT)
    if problems:
        print(f"读不到 CI 面，不落盘：{problems}")
        return 2
    out, unmapped = [], []
    for c in cmds:
        hit = classify(c["command"])
        if hit is None:
            unmapped.append((c["command"], 0))
            continue
        kind, cons, why, sub = hit
        out.append({"command": c["command"], "kind": kind,
                    "consumers": cons, "why": why, "matched_rule": sub})
    if unmapped:
        for cmd, n in unmapped:
            print(f"[UNMAPPED] 没有一条规则接住它（命中 {n}）：{cmd}")
        print("有任何一条命令没被唯一接住 ⇒ 一个字都不写")
        return 3
    out.sort(key=lambda e: e["command"])
    path = ROOT / csc.SURFACE_REGISTER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": out}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    n_ci = sum(1 for e in out if e["kind"] == "ci-only")
    print(f"写入 {path.relative_to(ROOT)}：{len(out)} 条（已接住 {len(out) - n_ci} / "
          f"结构性免跑 {n_ci}），CI 现读命令也是 {len(cmds)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
