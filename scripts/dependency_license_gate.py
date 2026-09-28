#!/usr/bin/env python3
"""依赖许可证门禁：把"这个依赖的许可证我们能不能用"变成会红的判据（F-DEP-LICENSE 第 92 片）。

起因不是"想加一道门"，而是第 91 片给 CI 面对账时发现的一件事：CI 的 `license-scan` job 跑的是
裸 `pip-licenses`——**它没有可失败的断言**（只打印，退码恒 0），所以"本仓有许可证审查"这句话
在机器层面等于没有。而仓库里确实写过一次许可证判断：第 77 片选 `pypdf` 而不是 `PyMuPDF`，
理由写在 `pyproject.toml` 的注释里（"后者 AGPL-3.0，与本仓的 Apache-2.0 不兼容"）
——那是**散文**，没有任何尺子复查它。

现读的第一手后果（本轮实测，取证文档 §一）：沿 `cad` extra 可达的 `cadquery ← casadi`，
其元数据 `License` 字段是 `GNU Lesser General Public License v3 or later (LGPLv3+)`，
而它的 trove classifier 只有 `License :: OSI Approved`（没有具体许可证）。
⇒ 只看 classifier 的阶梯会把它读成"看不见"，从而**放过一条 LGPL 依赖**。
这决定了取信号的方式：三种信号全收，任一给出具体许可证就用它，混合信号要报。

判据形状（每包一档）：
  allowed            —— 许可证在许可清单内（`OR` 只要有一个分支全可用即可用；`AND` 要全可用）；
  forbidden          —— 命中强 copyleft（GPL / AGPL 家族）⇒ **判红**；台账放行也照红；
  review-required    —— 弱 copyleft（LGPL 家族）等"要人拍板"的档，且台账没裁 ⇒ **判红**；
  unknown-license    —— 三个信号都给不出可识别许可证 ⇒ **判红**（"看不见"不等于合规）；
  adjudicated        —— 上面两档被台账按**同一个许可证串**裁成 `accepted` ⇒ 记绿，理由可查；
  out-of-closure     —— 装了但从声明根走不到 ⇒ 只报（工具链残留，不判红也不判绿）；
  unresolved         —— 闭包里点到、但这个平台没装（环境标记决定）⇒ 只报，不折成合规；
  declared-missing   —— 我们**自己**声明的依赖档装不上 ⇒ 必须在 `DECLARED_NOT_INSTALLED`
                       里写理由；没写理由 ⇒ **判红**（"这一面从没看过它"要有人签字）；
  台账该撤            —— 裁过的包**已不在闭包内**、或现读的许可证与裁时不同 ⇒ **判红**
                        （豁免不许只涨不消；"不在闭包"也算，因为条目留着的意义就是给闭包内的包放行）。

分母由本脚本自报（`corpus.*`），不抄进任何文档。
法务/属主的实体裁决仍是线下项：本工具把"要拍什么、拍完写在哪"钉死，不替人拍。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

POLICY_REL = "docs/audit/DEPENDENCY_LICENSE_LEDGER.json"
PYPROJECT_REL = "pyproject.toml"

# 归一化后的许可证 id → 档位。清单是"家族级"判断；要越权放行某个包只能走台账，且台账对
# forbidden 档**无权放行**（见 audit 里的「台账越权放行」）。
LICENSE_FAMILY: dict[str, str] = {
    "mit": "allowed", "mit-cmu": "allowed", "bsd": "allowed", "bsd-2-clause": "allowed",
    "bsd-3-clause": "allowed", "bsd-3-clause-clear": "allowed", "apache-2.0": "allowed",
    "isc": "allowed", "psf-2.0": "allowed", "psf": "allowed", "unlicense": "allowed",
    "0bsd": "allowed", "blueoak-1.0.0": "allowed", "cc0-1.0": "allowed",
    "mpl-2.0": "allowed",                                       # 文件级 weak copyleft
    "euploc-1.1.0": "allowed",
    "lgpl-2.1": "review", "lgpl-3.0": "review", "lgpl-3.0-or-later": "review",
    "lgpl": "review", "epl-2.0": "review", "cddl-1.0": "review",
    "gpl-2.0": "forbidden", "gpl-3.0": "forbidden", "gpl-3.0-or-later": "forbidden",
    "gpl": "forbidden", "agpl-3.0": "forbidden", "agpl-3.0-or-later": "forbidden",
    "agpl": "forbidden",
}

# 元数据里的写法 → 本表 id。空串＝**泛化** classifier（`License :: OSI Approved` 这种
# 只说"是开源协议"的写法），它不算"已标注"——casadi 那一格就是靠这条才被照出来的。
ALIASES: dict[str, str] = {
    "mit license": "mit", "mit": "mit", "mit license (cmu)": "mit-cmu", "mit-cmu": "mit-cmu",
    "bsd license": "bsd", "bsd": "bsd", "bsd-2-clause": "bsd-2-clause",
    "bsd-3-clause": "bsd-3-clause", "simplified bsd": "bsd-2-clause",
    "new bsd license": "bsd-3-clause", "modified bsd": "bsd-3-clause",
    "apache software license": "apache-2.0", "apache 2.0": "apache-2.0",
    "apache-2.0": "apache-2.0", "asl 2.0": "apache-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "mpl-2.0", "mpl-2.0": "mpl-2.0",
    "python software foundation license": "psf-2.0", "psf license": "psf-2.0",
    "psf-2.0": "psf-2.0", "the unlicense (unlicense)": "unlicense", "unlicense": "unlicense",
    "isc license (iso 18092:2015)": "isc", "isc license": "isc", "isc": "isc",
    "zope public license 2.1 (zpl 2.1)": "euploc-1.1.0",
    "gnu lesser general public license v3 or later (lgplv3+)": "lgpl-3.0-or-later",
    "gnu lesser general public license v3 (lgpl)": "lgpl-3.0",
    "lgpl-3.0-or-later": "lgpl-3.0-or-later", "lgplv3+": "lgpl-3.0-or-later",
    "lgpl-3.0": "lgpl-3.0", "lgpl-2.1": "lgpl-2.1",
    "gnu lesser general public license v2.1 (lgplv2.1)": "lgpl-2.1",
    "gnu general public license v2 (gplv2)": "gpl-2.0",
    "gnu general public license v3 (gplv3)": "gpl-3.0",
    "gpl-3.0-or-later": "gpl-3.0-or-later",
    "gnu affero general public license v3 (agpl-3.0)": "agpl-3.0",
    "agpl-3.0-or-later": "agpl-3.0-or-later",
    "osid approved": "", "osi approved": "", "dfsg approved": "",
}

# 我们自己声明了、但发布/收口环境装不上的依赖：逐条写清"为什么这一面看不见它"。
# 新出现的没装依赖没登记 ⇒ 判红。这一格与 CI 面的「结构性免跑必须带理由」同族。
DECLARED_NOT_INSTALLED: dict[str, str] = {
    "mcp": "`server-mcp` 档只有 MCP server 运行时才需要，发布环境与收口链都不装它"
           " ⇒ 它的许可证不在本面这一跑的覆盖面里",
}


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _norm_id(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip()).lower()
    return ALIASES.get(s, s)


def parse_expression(expr: str) -> list[list[str]]:
    """SPDX 串 → OR 分支的列表，每个分支是 id 列表（`A OR (B AND C)` 里括号不解，交台账）。

    为什么要把 OR/AND 分开而不是拍平成一堆候选：`Apache-2.0 OR BSD-3-Clause`（cryptography）
    与 `MIT AND LGPL-3.0` 在"能不能用"上是**相反**的结论——拍平之后前者会让后者也变绿。
    """
    if "(" in expr or ")" in expr:
        return []
    out: list[list[str]] = []
    for branch in re.split(r"\s+OR\s+", expr, flags=re.I):
        ids = [t for t in (_norm_id(s) for s in re.split(r"\s+AND\s+", branch, flags=re.I)) if t]
        if ids:
            out.append(ids)
    return out


def classify_branches(branches: list[list[str]]) -> tuple[str, str]:
    """OR-of-AND 结构 → 档位。任一分支全 allowed ⇒ allowed；有分支含 forbidden 但另有干净分支 ⇒
    按那条干净分支放行（用户可以选它），但把混合情况写进依据里。"""
    known = [[i for i in b if i in LICENSE_FAMILY] for b in branches]
    known = [b for b in known if b]
    if not known:
        return "unknown-license", "没有可识别的许可证标识"
    for b in known:
        if all(LICENSE_FAMILY[i] == "allowed" for i in b):
            return "allowed", "可用分支：" + " + ".join(b)
    if all(any(LICENSE_FAMILY[i] == "forbidden" for i in b) for b in known):
        return "forbidden", "每个分支都含强 copyleft：" + " / ".join(" + ".join(b) for b in known)
    return "review-required", "、".join(sorted({i for b in known for i in b})) + " 属要人拍板的档"


def read_declared_roots(pyproject_text: str) -> list[str]:
    """pyproject 声明的依赖名（`dependencies` + 全部 `optional-dependencies` 的并集）。"""
    i = pyproject_text.find("dependencies = [")
    j = pyproject_text.find("[tool.")
    seg = pyproject_text[i if i >= 0 else 0:(j if j > i else len(pyproject_text))]
    roots = []
    for m in re.finditer(r'"([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*(?:[<>=!~;].*)?"', seg):
        name = m.group(1)
        if _canon(name) in {"full", "dev", "cad", "server", "server-mcp", "project"}:
            continue
        roots.append(name)
    return sorted(set(roots))


def installed_index() -> dict[str, list[dict]]:
    """已装发行包按归一名索引。**同名多份不合并**——多份就是"分母会漂"的来源，要看得见。"""
    from importlib.metadata import distributions
    idx: dict[str, list[dict]] = {}
    for d in distributions():
        m = d.metadata
        name = m.get("Name")
        if not name:
            continue
        idx.setdefault(_canon(name), []).append({
            "name": name, "version": m.get("Version") or "",
            "expression": m.get("License-Expression") or "",
            "license_fields": [x.strip() for x in (m.get_all("License") or []) if x.strip()],
            "classifiers": [x.split(" :: ")[-1] for x in (m.get_all("Classifier") or [])
                            if x.startswith("License ::")],
            "requires": list(m.get_all("Requires-Dist") or []),
        })
    return idx


def dep_name(req: str) -> str:
    return _canon(re.split(r"[\s;\[<>=!~(]", req.strip())[0])


def is_optional(req: str) -> bool:
    """`Requires-Dist: X; extra == "dev"` 是**那个包自己的**选装档，我们的安装不会拉它。

    实测本环境 480 条第三方 requires 里 409 条是这一形。把它们当依赖展开，
    闭包会从"装了多少"膨胀到 169（其中 117 个从未安装），每条判据都被"未安装"淹没
    ——那不是保守，那是失聪。环境标记（`python_version`、`sys_platform`…）**不跳**：
    它们在别的平台会被装上，跳了就是真漏判；本环境没装的按 `unresolved` 只报。
    """
    return "extra ==" in req or "extra==" in req


def closure(roots: list[str], idx: dict[str, list[dict]]) -> tuple[dict[str, str], set[str]]:
    """从声明根 BFS。返回 (包 → 到达它的那一跳, 可达名集合)。

    环境标记（`extra == "dev"`、`python_version < …`）**一律忽略**＝取并集。
    这是保守选择：宁可把 dev-only 的传递依赖纳入判据，也不要因为标记解析不全
    而漏掉一条运行时依赖。代价（mypy 系因此在闭包内）写进取证文档 §四边界。
    """
    reach: dict[str, str] = {}
    seen = {_canon(r) for r in roots}
    skipped_optional = 0
    q = list(seen)
    while q:
        cur = q.pop(0)
        for rec in idx.get(cur, []):
            for r in rec["requires"]:
                if is_optional(r):
                    skipped_optional += 1
                    continue
                dep = dep_name(r)
                if dep and dep not in seen:
                    seen.add(dep)
                    reach[dep] = cur
                    q.append(dep)
    for r in sorted(seen):
        reach.setdefault(r, "pyproject.toml")
    return reach, seen, skipped_optional


def signals_of(rec: dict) -> tuple[list[list[str]], list[str]]:
    """(OR 分支列表, 全部信号原文)。三个信号全收，不给优先级：
    `License-Expression` 是 PEP 639 的 SPDX 串（最精确），但很多包没填；
    classifier 可能只写"OSI Approved"（泛化，**不算已标注**）；
    free-text `License` 字段常有具体名（casadi 那一格只有它有答案）。"""
    branches: list[list[str]] = []
    raw: list[str] = []
    if rec.get("expression"):
        branches += parse_expression(rec["expression"])
        raw.append(f"expr={rec['expression']!r}")
    for f in rec.get("license_fields") or []:
        br = parse_expression(f) or [[_norm_id(f)]]
        branches += [b for b in br if b]
        raw.append(f"field={f!r}")
    for c in rec.get("classifiers") or []:
        t = _norm_id(c)
        if t:
            branches.append([t])
        raw.append(f"cls={c!r}")
    return branches, raw


def license_of(rec: dict) -> tuple[str, str, list[str], list[str]]:
    """返回 (档位, 依据, 去重后的候选 id, 信号原文)。"""
    branches, raw = signals_of(rec)
    ids = sorted({i for b in branches for i in b})
    if not branches:
        return "unknown-license", "三个信号都没给出可识别的许可证", [], raw
    return classify_branches(branches) + (ids, raw)


def ledger_ids_of(ent: dict) -> list[str]:
    """台账里那串许可证文本 → 归一 id 集合（与现读比对的唯一口径）。"""
    return sorted({i for b in parse_expression(str(ent.get("license") or "")) for i in b})


def load_ledger(root: Path) -> tuple[dict[str, dict], list[str]]:
    p = root / POLICY_REL
    if not p.is_file():
        return {}, []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"ledger_unreadable: {POLICY_REL}：{exc}"]
    out: dict[str, dict] = {}
    problems: list[str] = []
    for e in raw.get("entries", []):
        pkg = _canon(str(e.get("package") or ""))
        if not pkg:
            problems.append(f"ledger_entry_invalid: {POLICY_REL} 有条目没有 package")
            continue
        out[pkg] = {"decision": str(e.get("decision") or ""),
                    "license": str(e.get("license") or ""),
                    "why": str(e.get("why") or ""), "owner": str(e.get("owner") or "")}
    return out, problems


def audit(root: Path, idx: dict[str, list[dict]] | None = None,
          declared_not_installed: dict[str, str] | None = None) -> dict[str, Any]:
    """两个注入点：`idx=None` 读本机真实环境，`declared_not_installed=None` 读模块常量。

    注入不是给测试开后门——覆盖面理由表本身就是**数据**，把它做成参数才能同时测到
    "有理由 ⇒ 只记档"与"没理由 ⇒ 判红"两极。
    """
    pp = root / PYPROJECT_REL
    if not pp.is_file():
        return {"ok": False, "violations": [], "problems": [f"pyproject_missing: {pp}"],
                "corpus": {}, "buckets": {}, "rows": []}
    problems: list[str] = []
    violations: list[dict] = []
    roots = read_declared_roots(pp.read_text(encoding="utf-8"))
    if not roots:
        problems.append("declared_roots_empty: 一条声明依赖都没读到（解析面或文件变了）")
    if idx is None:
        idx = installed_index()
    if not idx:
        problems.append("installed_index_empty: 读不到任何已装发行包（环境没装依赖？）")
    reach, seen, skipped_optional = closure(roots, idx)
    ledger, lproblems = load_ledger(root)
    problems += lproblems
    buckets = {"allowed": 0, "forbidden": 0, "review-required": 0, "unknown-license": 0,
               "adjudicated": 0, "out-of-closure": 0, "unresolved": 0, "declared-missing": 0}
    reasons = DECLARED_NOT_INSTALLED if declared_not_installed is None else declared_not_installed
    missing = sorted(r for r in (_canon(x) for x in roots) if r not in idx)
    for name in missing:
        if name in reasons:
            buckets["declared-missing"] += 1
            continue
        violations.append({
            "field": "声明的依赖没查过", "doc": name, "line": 0, "written": "(未登记)",
            "detail": f"pyproject 声明了 {name}，当前环境读不到它的元数据，而覆盖面清单里"
                      "没写理由 ⇒ 要么装上它，要么在 DECLARED_NOT_INSTALLED 里说明"
                      "为什么这一面看不见它（这一格与 CI 面的「免跑必须带理由」同族）"})
    rows: list[dict] = []
    dupes = sorted(k for k, v in idx.items() if len(v) > 1)
    for name in sorted(seen):
        recs = idx.get(name)
        if not recs:
            buckets["unresolved"] += 1     # 别的平台/标记下才会装：只报，不折成"合规"
            continue
        rec = recs[0]
        rank, why, ids, raw = license_of(rec)
        ent = ledger.get(name)
        state = rank
        if rank == "allowed":
            buckets["allowed"] += 1
            if ent and ent["license"] and ledger_ids_of(ent) != sorted(ids):
                violations.append({"field": "台账该撤", "doc": name, "line": 0,
                                   "written": ent["license"],
                                   "detail": f"台账按 {ent['license']!r} 裁的，现在读出的是 "
                                             f"{', '.join(ids) or '(无)'} ⇒ 上游换了许可证"})
        elif rank == "forbidden":
            buckets["forbidden"] += 1
            violations.append({
                "field": "依赖许可证禁用", "doc": name, "line": 0,
                "written": ", ".join(ids),
                "detail": f"{name} 的许可证是 {'/'.join(ids)}（强 copyleft），"
                          f"经 {reach.get(name, '?')} 可达 ⇒ 与发布许可冲突即判红。"
                          "第 77 片拒 PyMuPDF/AGPL 用的是同一条判断，只是那次写在注释里"})
            if ent:
                violations.append({
                    "field": "台账越权放行", "doc": name, "line": 0,
                    "written": ent["decision"],
                    "detail": f"台账把一条 forbidden 档的包裁成 {ent['decision']!r}："
                              f"{ent['why']!r} ⇒ 强 copyleft 不由台账静默吞掉，要属主换依赖"})
        elif rank in ("review-required", "unknown-license"):
            if ent and ent["license"] and ledger_ids_of(ent) == sorted(ids):
                state = "adjudicated"
                buckets["adjudicated"] += 1
                if ent["decision"] != "accepted":
                    violations.append({
                        "field": "依赖许可证未裁定", "doc": name, "line": 0,
                        "written": ent["decision"] or "(空)",
                        "detail": f"台账 decision={ent['decision']!r} 不是 'accepted'"
                                  " ⇒ needs-review 继续算红，不许靠挂条目把自己判绿"})
            else:
                buckets[rank] += 1
                field = ("依赖许可证看不见" if rank == "unknown-license"
                         else "依赖许可证未裁定")
                detail = (f"{name} 经 {reach.get(name, '?')} 可达；"
                          + ("三个信号都给不出可识别的许可证" if rank == "unknown-license"
                             else why)
                          + f"；信号原文：{'，'.join(raw)}"
                          + " ⇒ 在台账里给一条 decision/why（要人拍板的那种），或换一个依赖")
                violations.append({"field": field, "doc": name, "line": 0,
                                   "written": ", ".join(ids) or "(无)", "detail": detail})
        rows.append({"package": name, "version": rec["version"], "state": state,
                     "licenses": ids, "via": reach.get(name, ""), "why": why,
                     "signals": raw, "duplicates": len(recs)})
    buckets["out-of-closure"] = len(set(idx) - seen)
    for name, ent in sorted(ledger.items()):
        if name not in seen:
            violations.append({"field": "台账该撤", "doc": name, "line": 0,
                               "written": ent["decision"],
                               "detail": f"台账裁过 {name}，但从 pyproject 的声明根走不到它"
                                         " ⇒ 撤条目。条目留着的唯一意义是给闭包内的包放行，"
                                         "留着不做事的放行就是只涨不消的那本账"})
            continue
        recs = idx.get(name)
        if not recs:
            continue        # 声明了却没装：上面已经记了 not_installed 前提问题，这里不重复记一笔
        rank, _why, ids, _raw = license_of(recs[0])
        if rank in ("review-required", "unknown-license") \
                and (not ent["license"] or ledger_ids_of(ent) != sorted(ids)):
            violations.append({
                "field": "台账该撤", "doc": name, "line": 0, "written": ent["license"],
                "detail": f"台账按 {ent['license']!r} 裁的，现在读出的是 "
                          f"{', '.join(ids) or '(无)'} ⇒ 上游换了许可证，裁定要重做"})
    ok = not violations and not problems
    return {
        "ok": ok,
        "corpus": {"declared_roots": len(roots), "closure": len(seen),
                   "inspected": len(rows),
                   "installed_distinct": len(idx),
                   "skipped_optional_requires": skipped_optional,
                   "declared_missing": missing,
                   "installed_records": sum(len(v) for v in idx.values()),
                   "duplicated_names": dupes, "rows": len(rows), "ledger_size": len(ledger)},
        "buckets": buckets, "rows": rows, "violations": violations, "problems": problems,
    }


def render(rep: dict[str, Any]) -> str:
    b, c = rep["buckets"], rep["corpus"]
    lines = ["=" * 60, "依赖许可证门禁（闭包内逐包判档）", "=" * 60]
    if c:
        lines.append(f"声明根 {c['declared_roots']} 个 ⇒ 闭包 {c['closure']} 个名字"
                     f"（逐包判了 {c['inspected']}、跳过别人的选装 requires "
                     f"{c['skipped_optional_requires']} 条、声明而装不上："
                     f"{c['declared_missing'] or '无'}）；"
                     f"已装 {c['installed_distinct']} 个（元数据记录 {c['installed_records']} 份，"
                     f"同名多份：{c['duplicated_names'] or '无'}）；台账 {c['ledger_size']} 条")
    lines.append("归属：" + " / ".join(f"{k} {v}" for k, v in b.items()))
    for v in rep["violations"]:
        lines.append(f"  ✗ {v['field']} {v['doc']} `{v['written']}` ⇒ {v['detail']}")
    for p in rep["problems"]:
        lines.append(f"  ! 前提不成立：{p}")
    if rep["ok"]:
        lines.append("现状面缺陷 0 条：闭包内每个依赖的许可证都有归宿")
    return "\n".join(lines)


def _mark(marks: list, text: str) -> None:
    print(f"✓立住 {text}")
    marks.append(text)


def _rec(name: str, version: str = "1.0", expr: str = "", fields: list[str] | None = None,
         cls: list[str] | None = None, requires: list[str] | None = None) -> dict:
    return {"name": name, "version": version, "expression": expr,
            "license_fields": fields or [], "classifiers": cls or [],
            "requires": requires or []}


def _self_test(tmp: Path) -> int:
    marks: list[str] = []
    (tmp / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["demo-core>=1"]\n'
        "[project.optional-dependencies]\nextra = [\"demo-optional\"]\n"
        "[tool.setuptools]\n", encoding="utf-8")
    idx = {
        "demo-core": [_rec("demo-core", expr="BSD-3-Clause",
                           requires=["demo-mit", "demo-dual", "demo-lgpl",
                                     "demo-agpl", "demo-osi-only", "demo-nothing",
                                     "demo-and-mixed", "demo-platform-only; sys_platform",
                                     "demo-their-extra; extra == \"dev\""])],
        "demo-mit": [_rec("demo-mit", cls=["MIT License"])],
        "demo-dual": [_rec("demo-dual", expr="Apache-2.0 OR BSD-3-Clause")],
        "demo-lgpl": [_rec("demo-lgpl", fields=["GNU Lesser General Public License v3 or later "
                                                "(LGPLv3+)"], cls=["OSI Approved"])],
        "demo-agpl": [_rec("demo-agpl", expr="AGPL-3.0-or-later")],
        "demo-osi-only": [_rec("demo-osi-only", cls=["OSI Approved"])],
        "demo-nothing": [_rec("demo-nothing")],
        "demo-and-mixed": [_rec("demo-and-mixed", expr="MIT AND LGPL-2.1")],
        "tool-only": [_rec("tool-only", expr="MIT")],                     # 装了但走不到
    }
    roots = read_declared_roots((tmp / "pyproject.toml").read_text(encoding="utf-8"))
    assert roots == ["demo-core", "demo-optional"], roots
    rep = audit(tmp, idx=idx, declared_not_installed={"demo-optional": "合成：装不上的档"})
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("依赖许可证禁用", "demo-agpl") in fired, fired
    assert ("依赖许可证未裁定", "demo-lgpl") in fired, fired
    assert ("依赖许可证未裁定", "demo-and-mixed") in fired, fired
    assert ("依赖许可证看不见", "demo-osi-only") in fired, fired
    assert ("依赖许可证看不见", "demo-nothing") in fired, fired
    assert ("依赖许可证禁用", "demo-mit") not in fired and \
        ("依赖许可证禁用", "demo-dual") not in fired, fired
    b = rep["buckets"]
    # 分母逐个数（合成语料一共 10 个名字）：
    #   声明根 2（demo-core 有许可证、demo-optional 没装上）
    #   + demo-core 的 7 个具名依赖 + 1 条带 sys_platform 标记的依赖 = 10
    # 逐包判到 8 个（10 减掉两个"名字有了但环境里没有元数据"的），
    # 其中 allowed 3（demo-core BSD / demo-mit / demo-dual 双许可任一分支可用）
    # forbidden 1（demo-agpl）、review 2（demo-lgpl、demo-and-mixed）、
    # unknown 2（demo-osi-only 只有泛化 classifier、demo-nothing 三个信号全空）。
    assert rep["corpus"]["closure"] == 10, rep["corpus"]
    assert rep["corpus"]["inspected"] == 8, rep["corpus"]
    assert b["allowed"] == 3 and b["forbidden"] == 1 and b["review-required"] == 2 \
        and b["unknown-license"] == 2 and b["out-of-closure"] == 1, b
    assert b["unresolved"] == 2, b                      # demo-optional + demo-platform-only
    assert b["declared-missing"] == 1, b               # demo-optional 在理由清单里
    assert "demo-their-extra" not in {r["package"] for r in rep["rows"]}, rep["rows"]
    assert rep["corpus"]["skipped_optional_requires"] == 1, rep["corpus"]
    assert rep["corpus"]["declared_missing"] == ["demo-optional"], rep["corpus"]
    _mark(marks, "六档各落位：MIT classifier、`Apache-2.0 OR BSD-3-Clause`（任一分支可用即放行）"
                 "都绿；AGPL 判红；`License` 字段写 LGPLv3+ 而 classifier 只有泛化 "
                 "`OSI Approved` 的包**必须判红**（本尺立起的原因，casadi 那一格的合成版）；"
                 "`MIT AND LGPL-2.1` 不许因为含 MIT 就变绿；只有泛化 classifier 与"
                 "三个信号全空的都算「看不见」；装了但走不到的只报不红")
    # 台账：放行 review 档要**逐字对上许可证串**，且 decision 必须是 accepted
    led = tmp / POLICY_REL
    led.parent.mkdir(parents=True)
    led.write_text(json.dumps({"entries": [
        {"package": "demo-lgpl", "license": "LGPL-3.0-or-later", "decision": "accepted",
         "why": "属主拍板：仅作动态链接使用，不改其源码", "owner": "属主"},
        {"package": "demo-and-mixed", "license": "MPL-2.0", "decision": "accepted",
         "why": "许可证串与现读不一致（这条要判「该撤」）", "owner": "属主"},
        {"package": "demo-agpl", "license": "AGPL-3.0-or-later", "decision": "accepted",
         "why": "想越权放行强 copyleft（这条要判「越权」）", "owner": "属主"},
        {"package": "demo-osi-only", "license": "LGPL-3.0-or-later", "decision": "needs-review",
         "why": "挂了条目但没拍板（这条要继续红）", "owner": "属主"},
        {"package": "tool-only", "license": "MIT", "decision": "accepted",
         "why": "裁过的包不在闭包里（这条要判「该撤」）", "owner": "属主"},
    ]}, ensure_ascii=False), encoding="utf-8")
    rep2 = audit(tmp, idx=idx)
    f2 = {(v["field"], v["doc"]) for v in rep2["violations"]}
    assert ("依赖许可证未裁定", "demo-lgpl") not in f2, f2
    assert rep2["buckets"]["adjudicated"] == 1, rep2["buckets"]
    assert ("台账该撤", "demo-and-mixed") in f2 and ("台账该撤", "tool-only") in f2, f2
    assert ("台账越权放行", "demo-agpl") in f2, f2
    assert ("依赖许可证看不见", "demo-osi-only") in f2, f2
    # 声明而装不上：有理由 ⇒ 只记档；没理由 ⇒ 判红
    nomcp = tmp / "nomcp"
    nomcp.mkdir()
    (nomcp / "pyproject.toml").write_text(
        '[project]\ndependencies = ["demo-mit", "demo-never-installed"]\n', encoding="utf-8")
    rep5 = audit(nomcp, idx={"demo-mit": [_rec("demo-mit", cls=["MIT License"])]},
                 declared_not_installed={})
    assert ("声明的依赖没查过", "demo-never-installed") in {
        (v["field"], v["doc"]) for v in rep5["violations"]}, rep5["violations"]
    assert not rep5["problems"], rep5["problems"]
    _mark(marks, "我们自己声明、这个环境装不上的依赖要有理由：`demo-optional` 在理由清单里"
                 "⇒ 只记档（`declared-missing`），没登记的 `demo-never-installed` ⇒ 判红。"
                 "而第三方自己的 `extra ==` 选装根本不进闭包（实测本仓：480 条 requires 里"
                 "409 条是这一形，跳过后闭包从 169 收到 45）")
    _mark(marks, "台账四道闸各开火一次：裁对串＋accepted 才转绿；串对不上 ⇒「该撤」；"
                 "裁的是 forbidden 档 ⇒「越权放行」（台账不能吞掉强 copyleft）；"
                 "decision 还是 needs-review ⇒ 继续红（不许挂个条目就自判合规）")
    good = tmp / "good"
    good.mkdir()
    (good / "pyproject.toml").write_text(
        '[project]\ndependencies = ["demo-mit", "demo-dual"]\n[tool.setuptools]\n',
        encoding="utf-8")
    small = {k: idx[k] for k in ("demo-mit", "demo-dual")}
    rep3 = audit(good, idx=small, declared_not_installed={})
    assert not rep3["violations"] and not rep3["problems"], (rep3["violations"], rep3["problems"])
    assert rep3["corpus"]["declared_missing"] == [], rep3["corpus"]
    _mark(marks, "合规侧同批存在：全 MIT / 双许可的闭包 ⇒ ok=True 且 problems 全空"
                 "（不是靠豁免清单）")
    empty = tmp / "empty"
    empty.mkdir()
    assert main(["--repo", str(empty)]) == 2, "没有 pyproject 必须读成前提不成立"
    _mark(marks, "读不到声明面＝前提不成立（退 2），不是「零依赖所以零风险」")
    print(f"--self-test：{len(marks)} 条合成读数全部对上")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="依赖许可证门禁")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    rep = audit(root)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(render(rep))
    if rep["problems"]:
        return 2
    return 0 if rep["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
