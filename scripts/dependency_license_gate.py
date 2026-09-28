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
                        （豁免不许只涨不消；"不在闭包"也算，因为条目留着的意义就是给闭包内的包放行）;
  许可证正文与元数据打架 —— **第 93 片**加的正文面：轮子里打包的许可证文件（只认
                        `*.dist-info/**` 下的 LICENSE*/COPYING*，包树里的是 vendored 第三方）
                        断言的档位比元数据三个信号**更严** ⇒ **判红**（"元数据写 MIT、
                        正文是 AGPL"是上游低报，不是我们的口径松）。反向（正文更宽）只记档；
                        正文里**提及**（不在标题也不在头部窗口）的更严家族只记档——
                        实测这样才不会把 `typing-extensions`（PSF 正文提到 GPL）
                        与 `cadquery-ocp` 的 `LICENSES_bundled`（列了 AGPL）误读成禁用；
  正文看不见 / 正文认不出 —— 轮子里没有 dist-info 正文（实测 `casadi`：58 个包树内的
                        vendored 许可证、0 个自己的正文）或有正文但没有一条断言认得出来 ⇒
                        **只报**，不折成合规；
  同名多份元数据不一致   —— 一个包名在这个环境有多份发行记录（实测 `aipd-os` 是
                        wheel 的 `.dist-info` 加遗留的 `src/aipd_os.egg-info`）且两份给出的
                        许可证不同 ⇒ **判红**，并按**最严**的那份判档。

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


# ---- 正文（wheel 里打包的许可证文本）这一面：第 93 片 ----
#
# 为什么要两级而不是"全文扫一遍"：实测本闭包 48 个正文文件里，全文短语匹配会把
# `typing-extensions` 读成 GPL+ISC（PSF 许可证正文里**提到** GPL），把 `cadquery-ocp` 的
# `LICENSES_bundled` 读成 8 个家族（含 AGPL）——那是**提及**，不是这个包给自己选的许可证。
# 所以：出现在**行首标题**或文件头部窗口里才算"断言"（拿它跟元数据比严重度），
# 只在正文中间出现的算"提及"（更严的一律只报，不折成红也不折成绿）。
# 借的思路来自 scancode 的规则分层（标题/正文分档），未引它的实现：
# scancode-toolkit 32.5.0 与 spdx-tools 0.8.5 都 `requires_python >=3.10`，
# 而本仓 `.venv` 实测是 3.9.6 ⇒ 结构上装不进来。
BODY_NAME_RE = re.compile(r"^(LICENSE|LICEN[CS]E[-.\w]*|COPYING[-.\w]*)$", re.I)
# **标题行**：某一行**以**这一串开头才算"这个文件就是这份许可证的正文"。
# 为什么要行首而不是窗口内出现：实测 bundled 声明文件用 `license: GNU AFFERO GENERAL
# PUBLIC LICENSE` 这种**键值行**列举别人家的许可证——窗口判据会把它读成"本包的许可证"，
# 于是 BSD 的包只因附带一份 vendored AGPL 声明就判红（那是误报，不是发现）。
BODY_TITLE: dict[str, list[str]] = {
    "mit": ["mit license", "the mit license"],
    "apache-2.0": ["apache license"],
    "bsd": ["bsd license", "bsd-3-clause", "bsd 3-clause", "the bsd license",
            "new bsd license", "simplified bsd license"],
    "mpl-2.0": ["mozilla public license"],
    "lgpl-3.0-or-later": ["gnu lesser general public license"],
    "gpl-3.0-or-later": ["gnu general public license"],
    "agpl-3.0-or-later": ["gnu affero general public license"],
    "psf-2.0": ["python software foundation license"],
    "isc": ["isc license"],
    "unlicense": ["the unlicense", "unlicense"],
    "euploc-1.1.0": ["end-user package license agreement"],
}
# **操作性条款**：没有标题行的正文（BSD 体例、MIT 只写版权声明那种）靠单行里的
# 独有句式认。这些句子只可能出现在许可证正文自身里，不会出现在"license: X"式列举里。
BODY_GRANT: dict[str, list[str]] = {
    "mit": ["permission is hereby granted, free of charge"],
    "bsd": ["redistribution and use in source and binary forms",
            "this software is provided by the copyright holders and contributors"],
    "isc": ["permission to use, copy, modify, and/or distribute"],
    "apache-2.0": ["terms and conditions for use, reproduction, and distribution"],
    "mpl-2.0": ["governed by the mozilla public license"],
    "unlicense": ["this is free and unencumbered software released into the public domain"],
    "lgpl-3.0-or-later": ["permissions hereby granted to link"],
    "psf-2.0": ["this agreement is between the python software foundation"],
}
# 档位严重度序：正文比元数据**更严**才判红（元数据低报才是要拦的方向）。
# 两种拼写都收：`classify_branches` 产出 `review-required`，`LICENSE_FAMILY` 的值是 `review`。
SEVERITY = {"allowed": 0, "review": 1, "review-required": 1, "forbidden": 2}
# 粗粒度标识符 → 它覆盖的细粒度写法。classifier 常只给 `BSD License`（归一后 `bsd`），
# 而台账里人写的是 `BSD-3-Clause`；不做这层覆盖，"元数据只给粗名"的包（实测 numpy、
# reportlab、pycparser、pygments、pypdf 都这一形）挂上裁定条目也永远判「该撤」。
COARSE: dict[str, set[str]] = {
    "bsd": {"bsd", "bsd-2-clause", "bsd-3-clause", "bsd-3-clause-clear"},
    "lgpl-3.0-or-later": {"lgpl-3.0-or-later", "lgpl-3.0", "lgpl"},
    "lgpl-3.0": {"lgpl-3.0", "lgpl"},
    "lgpl-2.1": {"lgpl-2.1", "lgpl"},
    "gpl-3.0-or-later": {"gpl-3.0-or-later", "gpl-3.0", "gpl"},
    "gpl-3.0": {"gpl-3.0", "gpl"},
    "gpl-2.0": {"gpl-2.0", "gpl"},
    "agpl-3.0-or-later": {"agpl-3.0-or-later", "agpl-3.0", "agpl"},
    "psf-2.0": {"psf-2.0", "psf"},
    "mit": {"mit"},
}


def ledger_covers(led_ids: list[str], ids: list[str]) -> bool:
    """台账裁的每个 id 都要被现读的 id 面**覆盖**（同串，或由某个粗名展开）。"""
    expanded = set(ids)
    for tok in ids:
        expanded |= COARSE.get(tok, set())
    return all(x in expanded for x in led_ids)


# LGPL 许可证正文按 FSF 的写法必然逐字引用 GPL；断言里有 lgpl 时，提及里的 gpl 不算"另有更严声明"。
COPYLEFT_PARENT = {"lgpl-3.0-or-later": "gpl-3.0-or-later", "lgpl-3.0": "gpl-3.0",
                   "lgpl-2.1": "gpl-2.0", "lgpl": "gpl"}


def detect_body(text: str) -> tuple[list[str], list[str]]:
    """正文文本 → (断言到的家族, 只在正文里提及的家族)，都按 id 排序。

    断言＝**标题行行首**命中或**操作性条款**命中；提及＝全文子串命中但没到断言的形状。
    """
    flat = re.sub(r"\s+", " ", text or "").lower()
    lines = [ln.strip().lower() for ln in (text or "").splitlines() if ln.strip()]
    # 只认**文件头部**（前 8 个非空行）里的证据为"断言"。实测理由：numpy 的 dist-info 正文
    # 第 3 行是它自己的 BSD 条款，第 140/210 行才出现 `GNU GENERAL PUBLIC LICENSE`
    # ——那是它 quoted 进来的 GPL 全文；不限头部就会把 BSD 的 numpy 判成"正文比元数据严"。
    head = lines[:8]
    asserted: set[str] = set()
    mentioned: set[str] = set()
    fams = sorted(set(BODY_TITLE) | set(BODY_GRANT))
    for fam in fams:
        titles = BODY_TITLE.get(fam, [])
        grants = BODY_GRANT.get(fam, [])
        on_line = any(ln.startswith(t) for ln in head for t in titles)
        clause = any(any(g in ln for g in grants) for ln in head)
        if on_line or clause:
            asserted.add(fam)
        elif any(p in flat for p in titles + grants):
            mentioned.add(fam)
    for fam in list(asserted):                        # LGPL 引用 GPL：不算两码事
        parent = COPYLEFT_PARENT.get(fam)
        if parent:
            mentioned.discard(parent)
            asserted.discard(parent)
    return sorted(asserted), sorted(mentioned)


def installed_bodies() -> dict[str, list[tuple[str, str]]]:
    """已装发行包**自己**的许可证正文：只取 `*.dist-info/**` 下的 LICENSE*/COPYING*。

    包树里的同名文件一律不算——实测 `casadi` 有 58 个 `include/licenses/*`（全是它
    vendored 的第三方许可证）、`numpy` 有 3 个包树内的 LICENSE、`reportlab` 的
    `fonts/DarkGarden-copying-gpl.txt` 是字体许可证；把它们当"这个包的许可证"，
    BSD 的 reportlab 就会读成 GPL——那是误报，不是发现。
    """
    from importlib.metadata import distributions
    out: dict[str, list[tuple[str, str]]] = {}
    for d in distributions():
        name = _canon(d.metadata.get("Name") or "")
        if name:
            out.setdefault(name, []).extend(bodies_of(d))
    return out


def bodies_of(dist: Any) -> list[tuple[str, str]]:
    """单个发行包的正文收集（`installed_bodies` 的真实循环体，单独成函数是为了能拿**真**
    dist-info 目录测：`Distribution.at()` 造的临时包不需要任何注入就能走这条读文件的路。"""
    found: list[tuple[str, str]] = []
    for f in (dist.files or []):
        parts = [x for x in f.as_posix().split("/") if x]
        if not parts or not BODY_NAME_RE.match(parts[-1]):
            continue
        if not any(".dist-info" in x for x in parts):
            continue
        try:
            loc = Path(str(f.locate()))
        except Exception:                              # noqa: BLE001 - 不可解析只算看不见
            continue
        if not loc.is_file():
            continue
        try:
            found.append((f.as_posix(), loc.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return found


def ids_are_tokens(ids: list[str]) -> list[str]:
    """元数据信号清洗：只留**像 SPDX 短标识符**的串。

    实测本闭包有 4 个包的 `License` 字段是整段许可证全文（numpy / multimethod /
    reportlab / cadquery），原文进 ids 之后，台账那侧"逐字对上许可证串"在数学上不可能满足
    ⇒ 裁不动、永远红。清洗只影响展示与台账比对，不改档位（档位早就按"认得出的才计"判）。
    """
    return [i for i in ids if len(i) <= 40 and re.fullmatch(r"[A-Za-z0-9.+:_()/-]+", i)]



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


def package_license(recs: list[dict]) -> tuple[str, str, list[str], list[str], bool]:
    """同名多份元数据记录 → 一个说法：档位取**最严**、id 取**并集**，并报"记数不一致"。

    真读到的形态（第 93 片实测）：`aipd-os` 在本环境有**两份**记录——wheel 的
    `.venv/.../aipd_os-5.6.0.dist-info`（11 个文件）与遗留的 `src/aipd_os.egg-info`（206 个）。
    取第一份＝拿"恰好排在前面那份"当结论；两份要是一份写 MIT 一份写 AGPL，
    宽松那份会静默盖掉严格那份。分母仍按**名字**计一次（`inspected` 不翻倍），
    不一致的名字进 `corpus.duplicate_conflicts`。
    """
    per = [license_of(r) for r in recs]
    rank, why = per[0][0], per[0][1]
    for p in per[1:]:
        if SEVERITY.get(p[0], -1) > SEVERITY.get(rank, -1):
            rank, why = p[0], f"同名 {len(recs)} 份记录里取最严的一档：{p[1]}"
    ids = ids_are_tokens(sorted({i for p in per for i in p[2]}))
    raw = [s for p in per for s in p[3]]
    # 只有**档位**不同才算"两种说法"：`bsd` 与 `bsd-3-clause` 是同族的两种写法，
    # 按 id 面判会让所有"classifier+SPDX 双写"的包都开火（那是噪声，不是发现）。
    conflict = len({p[0] for p in per}) > 1
    return rank, why, ids, raw, conflict


def ledger_ids_of(ent: dict) -> list[str]:
    """台账里那串许可证文本 → 归一 id 集合（与现读比对的唯一口径）。"""
    return sorted({i for b in parse_expression(str(ent.get("license") or "")) for i in b})


def body_face(files: list[tuple[str, str]], meta_rank: str, meta_why: str) -> dict[str, Any]:
    """把一个包的正文与它的元数据对一次账。返回格子信息 + 要开的火。

    只在"正文比元数据**更严**"时判红：那是元数据低报（真风险，"MIT 其实 AGPL"）。
    反向（正文比元数据宽松）只记档——它不改变"我们能不能用"的答案，只是上游写得保守。
    元数据本身"看不见"（`unknown-license`）时不做比对：那一格已经为"看不见"红了，
    正文在这里是**补强**而不是冲突。
    """
    out: dict[str, Any] = {"state": "checked", "asserted": [], "mentioned": [],
                           "files": [n for n, _t in files], "violations": [],
                           "severe_mention": False, "looser": False}
    if not files:
        out["state"] = "missing"
        out["detail"] = "轮子里没有 dist-info 许可证正文"
        return out
    asserted: set[str] = set()
    mentioned: set[str] = set()
    for _n, text in files:
        a, m = detect_body(text)
        asserted |= set(a)
        mentioned |= set(m)
    out["asserted"], out["mentioned"] = sorted(asserted), sorted(mentioned)
    body_sev = max([SEVERITY.get(LICENSE_FAMILY.get(f, ""), -1) for f in asserted],
                   default=-1)                       # 无断言时不与元数据比档，但提及仍要算
    if not asserted:
        out["state"] = "unrecognized"
    if meta_rank not in SEVERITY:
        return out
    meta_sev = SEVERITY[meta_rank]
    if not asserted:
        worse = [f for f in mentioned
                 if SEVERITY.get(LICENSE_FAMILY.get(f, ""), -1) > meta_sev]
        if worse:
            out["severe_mention"] = True
            out["severe_mentions"] = worse
        return out
    if body_sev > meta_sev:
        out["violations"].append({
            "field": "许可证正文与元数据打架", "doc": "", "line": 0,
            "written": "正文 " + "/".join(asserted) + " vs 元数据 " + (meta_why or meta_rank),
            "detail": f"打包进轮子的许可证正文断言的是 {'/'.join(asserted)}（档 "
                      f"{_rank_name(body_sev)}），而元数据三个信号只给到 "
                      f"{meta_rank} ⇒ 上游自述低报了许可证，按正文这一档重判；"
                      "正文文件：" + ", ".join(out["files"])})
    elif body_sev < meta_sev:
        out["looser"] = True
    worse = [f for f in mentioned
             if SEVERITY.get(LICENSE_FAMILY.get(f, ""), -1) > max(body_sev, meta_sev)]
    if worse:
        out["severe_mention"] = True
        out["severe_mentions"] = worse
    return out


def _rank_name(sev: int) -> str:
    return {0: "allowed", 1: "review-required", 2: "forbidden"}.get(sev, "?")


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
          declared_not_installed: dict[str, str] | None = None,
          bodies: dict[str, list[tuple[str, str]]] | None = None) -> dict[str, Any]:
    """三个注入点：`idx=None` 读本机元数据，`declared_not_installed=None` 读模块常量，
    `bodies=None` 读本机 wheel 里的许可证正文（`installed_bodies()`）。

    注入不是给测试开后门——覆盖面理由表与正文面都是**数据**，做成参数才能同时测到
    "有理由 ⇒ 只记档"与"没理由 ⇒ 判红"两极、"正文是 MIT ⇒ 不红"与"正文是 AGPL ⇒ 红"两极。
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
    if bodies is None:
        bodies = installed_bodies()
    reach, seen, skipped_optional = closure(roots, idx)
    ledger, lproblems = load_ledger(root)
    problems += lproblems
    buckets = {"allowed": 0, "forbidden": 0, "review-required": 0, "unknown-license": 0,
               "adjudicated": 0, "out-of-closure": 0, "unresolved": 0, "declared-missing": 0,
               "body-checked": 0, "body-missing": 0, "body-unrecognized": 0,
               "body-severe-mention": 0, "body-looser-than-metadata": 0,
               "duplicate-records": 0, "duplicate-conflict": 0}
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
    dup_conflicts: list[str] = []
    dupes = sorted(k for k, v in idx.items() if len(v) > 1)
    for name in sorted(seen):
        recs = idx.get(name)
        if not recs:
            buckets["unresolved"] += 1     # 别的平台/标记下才会装：只报，不折成"合规"
            continue
        rec = recs[0]
        rank, why, ids, raw, conflict = package_license(recs)
        if len(recs) > 1:
            if conflict:
                buckets["duplicate-conflict"] += 1
                dup_conflicts.append(name)
                violations.append({
                    "field": "同名多份元数据不一致", "doc": name, "line": 0,
                    "written": f"{len(recs)} 份记录",
                    "detail": f"{name} 在这个环境里有 {len(recs)} 份元数据记录"
                              f"（{'；'.join(r['name'] + '/' + r['version'] for r in recs)}）"
                              f"而它们给出的许可证不一样 ⇒ 取最严的一档判定，"
                              "并把重复的安装记录清掉（遗留 egg-info 与 wheel 并存，"
                              "数学上等于「同一依赖两种说法」）"})
        body = body_face(bodies.get(name) or [], rank, why)
        if body["state"] == "checked":
            buckets["body-checked"] += 1
        elif body["state"] == "missing":
            buckets["body-missing"] += 1
        elif body["state"] == "unrecognized":
            buckets["body-unrecognized"] += 1
        if body["severe_mention"]:
            buckets["body-severe-mention"] += 1
        if body["looser"]:
            buckets["body-looser-than-metadata"] += 1
        for v in body["violations"]:
            v["doc"] = name
            violations.append(v)
        ent = ledger.get(name)
        state = rank
        if rank == "allowed":
            buckets["allowed"] += 1
            if ent and ent["license"] and not ledger_covers(ledger_ids_of(ent), ids):
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
                     "signals": raw, "duplicates": len(recs), "body": body})
    buckets["out-of-closure"] = len(set(idx) - seen)
    buckets["duplicate-records"] = len(dupes)
    for name in dupes:
        if name in seen:
            continue                       # 闭包内那圈已经判过
        _r, _w, _i, _s, conflict = package_license(idx[name])
        if conflict:
            buckets["duplicate-conflict"] += 1
            dup_conflicts.append(name)
            violations.append({
                "field": "同名多份元数据不一致", "doc": name, "line": 0,
                "written": f"{len(idx[name])} 份记录（闭包外）",
                "detail": f"{name} 有 {len(idx[name])} 份元数据记录且档位不一致；"
                          "它虽然从声明根走不到，但同一环境里两种说法本身就是"
                          "覆盖面漂移的来源 ⇒ 清掉重复安装记录"})
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
        rank, _why, ids, _raw, _c = package_license(recs)
        if rank in ("review-required", "unknown-license") \
                and (not ent["license"] or not ledger_covers(ledger_ids_of(ent), ids)):
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
                   "duplicated_names": dupes,
                   "body_files": sum(len(bodies.get(n, [])) for n in seen),
                   "duplicate_conflicts": dup_conflicts,
                   "rows": len(rows), "ledger_size": len(ledger)},
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
    if c:
        lines.append(f"正文面：闭包内读到 {c['body_files']} 个 dist-info 许可证文件"
                     f"（断言可比 {b['body-checked']}、无正文 {b['body-missing']}、"
                     f"认不出 {b['body-unrecognized']}、正文另有更严声明 "
                     f"{b['body-severe-mention']}、正文比元数据宽 "
                     f"{b['body-looser-than-metadata']}）；"
                     f"同名多份（全量名册）{b['duplicate-records']} 个、说法不一致 "
                     f"{b['duplicate-conflict']} 个：{c['duplicate_conflicts'] or '无'}")
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
    rep = audit(tmp, idx=idx, declared_not_installed={"demo-optional": "合成：装不上的档"},
                bodies={})
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
    rep2 = audit(tmp, idx=idx, bodies={})
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
                 declared_not_installed={}, bodies={})
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
    rep3 = audit(good, idx=small, declared_not_installed={}, bodies={})
    assert not rep3["violations"] and not rep3["problems"], (rep3["violations"], rep3["problems"])
    assert rep3["corpus"]["declared_missing"] == [], rep3["corpus"]
    _mark(marks, "合规侧同批存在：全 MIT / 双许可的闭包 ⇒ ok=True 且 problems 全空"
                 "（不是靠豁免清单）")
    # ---- 正文面（第 93 片）：断言/提及两级，只有"正文比元数据更严"才判红 ----
    body = tmp / "body"
    body.mkdir()
    (body / "pyproject.toml").write_text(
        '[project]\ndependencies = ["b-mit","b-lies","b-lgpl","b-bundle","b-nobody",'
        '"b-odd","b-dualrec"]\n', encoding="utf-8")
    MIT_TEXT = ("MIT License\n\nCopyright (c) 2020 someone\n\n"
                "Permission is hereby granted, free of charge, to any person obtaining a copy\n")
    AGPL_TEXT = ("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007\n\n"
                 "Copyright (C) 2007 Free Software Foundation, Inc.\n")
    LGPL_TEXT = ("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n\n"
                 "Copyright (C) 2007 Free Software Foundation, Inc.\n"
                 "This version of the GNU Lesser General Public License incorporates\n"
                 "the terms and conditions of version 3 of the GNU General Public\n"
                 "License, supplemented by the additional permissions listed below.\n")
    BUNDLE_TEXT = ("This wheel distribution bundles a number of libraries\n"
                   "that are compatibly licensed. We list them here.\n\n"
                   "name: someothersub\nfiles: pkg/_vendor/*\n"
                   "license: GNU AFFERO GENERAL PUBLIC LICENSE\n")
    bidx = {
        "b-mit": [_rec("b-mit", expr="MIT")],
        "b-lies": [_rec("b-lies", expr="MIT")],              # 元数据说 MIT，正文是 AGPL
        "b-lgpl": [_rec("b-lgpl", expr="LGPL-3.0-or-later")],
        "b-bundle": [_rec("b-bundle", expr="Apache-2.0")],
        "b-nobody": [_rec("b-nobody", expr="MIT")],
        "b-odd": [_rec("b-odd", expr="MIT")],
        "b-dualrec": [_rec("b-dualrec", expr="MIT"), _rec("b-dualrec", expr="AGPL-3.0-or-later")],
    }
    bodies = {
        "b-mit": [("b_mit-1.0.dist-info/licenses/LICENSE", MIT_TEXT)],
        "b-lies": [("b_lies-1.0.dist-info/licenses/LICENSE", AGPL_TEXT)],
        "b-lgpl": [("b_lgpl-1.0.dist-info/licenses/LICENSE", LGPL_TEXT)],
        "b-bundle": [("b_bundle-1.0.dist-info/LICENSE", BUNDLE_TEXT),
                     ("b_bundle-1.0.dist-info/LICENSES_bundled", BUNDLE_TEXT)],
        "b-odd": [("b_odd-1.0.dist-info/LICENSE", "Some proprietary notice, no known family.\n")],
        "b-dualrec": [("b_dualrec-1.0.dist-info/licenses/LICENSE", MIT_TEXT)],
    }
    rep6 = audit(body, idx=bidx, declared_not_installed={}, bodies=bodies)
    f6 = {(v["field"], v["doc"]) for v in rep6["violations"]}
    assert ("许可证正文与元数据打架", "b-lies") in f6, f6
    assert ("许可证正文与元数据打架", "b-mit") not in f6, f6
    assert ("许可证正文与元数据打架", "b-bundle") not in f6, f6
    b6 = rep6["buckets"]
    assert b6["body-checked"] == 4 and b6["body-missing"] == 1, b6
    assert b6["body-unrecognized"] == 2, b6                       # b-bundle + b-odd
    assert b6["body-severe-mention"] == 1, b6            # 只有 b-bundle 落在"提及"档
    assert b6["body-looser-than-metadata"] == 1, b6      # 两份记录取最严后正文反而宽
    lgpl_row = [r for r in rep6["rows"] if r["package"] == "b-lgpl"][0]
    assert lgpl_row["body"]["asserted"] == ["lgpl-3.0-or-later"], lgpl_row["body"]
    assert "gpl-3.0-or-later" not in lgpl_row["body"]["mentioned"], lgpl_row["body"]
    samefam = {"b-dualrec": [_rec("b-dualrec", cls=["BSD License"]),
                             _rec("b-dualrec", expr="BSD-3-Clause")]}
    rep6b = audit(body, idx=samefam, declared_not_installed={},
                  bodies={"b-dualrec": [("d.dist-info/LICENSE", MIT_TEXT)]})
    assert ("同名多份元数据不一致", "b-dualrec") not in {
        (v["field"], v["doc"]) for v in rep6b["violations"]}, rep6b["violations"]
    assert rep6b["corpus"]["duplicate_conflicts"] == [], rep6b["corpus"]
    assert ("同名多份元数据不一致", "b-dualrec") in f6, f6
    assert ("依赖许可证禁用", "b-dualrec") in f6, f6      # 取最严那份 ⇒ AGPL 档
    assert rep6["corpus"]["inspected"] == 7, rep6["corpus"]
    assert rep6["corpus"]["duplicate_conflicts"] == ["b-dualrec"], rep6["corpus"]
    assert b6["duplicate-records"] == 1 and b6["duplicate-conflict"] == 1, b6
    _mark(marks, "正文面两极：元数据 MIT 而正文 AGPL ⇒ 判红；同一份 AGPL 文字出现在"
                 "bundled 声明文件的**正文中间**（标题行没有家族名）⇒ 只记 `body-severe-mention`、"
                 "不开火（实测本仓 cadquery-ocp 就是这个形状）；LGPL 正文按 FSF 写法必然引用 GPL ⇒ "
                 "断言只算 lgpl、gpl 连提及都不算（少了这条，LGPL 依赖会二次误红）；"
                 "轮子里没正文（casadi 形）与正文认不出（专有声明形）都只报，不折成合规")
    _mark(marks, "同名多份元数据记录取**最严**一份判档并开火：MIT + AGPL 两份记录 ⇒ 既是"
                 "「同名多份元数据不一致」也是「依赖许可证禁用」，而分母只按名字计一次"
                 "（实测本仓 aipd-os 有 wheel 的 .dist-info 与遗留 src/aipd_os.egg-info 两份）")
    # 台账要比的 id 必须是**标识符**：整段许可证全文当 id 时，逐字对上串在数学上不可能满足
    idtree = tmp / "ids"
    idtree.mkdir()
    (idtree / "pyproject.toml").write_text('[project]\ndependencies = ["b-para"]\n',
                                           encoding="utf-8")
    para = ("Copyright (c) 2005-2024, somebody. All rights reserved.\n"
            "Redistribution and use in source and binary forms, with or without\n"
            "modification, are permitted provided that the following conditions\n")
    pidx = {"b-para": [_rec("b-para", cls=["BSD License"], fields=[para])]}
    rep7 = audit(idtree, idx=pidx, declared_not_installed={}, bodies={})
    row7 = [r for r in rep7["rows"] if r["package"] == "b-para"][0]
    assert row7["licenses"] == ["bsd"], row7["licenses"]
    assert not rep7["violations"], rep7["violations"]
    (idtree / POLICY_REL).parent.mkdir(parents=True)
    (idtree / POLICY_REL).write_text(json.dumps({"entries": [
        {"package": "b-para", "license": "BSD-3-Clause", "decision": "accepted",
         "why": "整段全文不该挡住裁定", "owner": "属主"}]}, ensure_ascii=False),
        encoding="utf-8")
    rep8 = audit(idtree, idx=pidx, declared_not_installed={}, bodies={})
    assert not rep8["violations"], rep8["violations"]      # 粗名 `bsd` 覆盖细串 BSD-3-Clause
    assert rep8["buckets"]["allowed"] == 1, rep8["buckets"]
    drift = json.loads((idtree / POLICY_REL).read_text(encoding="utf-8"))
    drift["entries"][0]["license"] = "MIT"                 # 换族：仍然要判「该撤」
    (idtree / POLICY_REL).write_text(json.dumps(drift, ensure_ascii=False), encoding="utf-8")
    rep9 = audit(idtree, idx=pidx, declared_not_installed={}, bodies={})
    assert ("台账该撤", "b-para") in {(v["field"], v["doc"]) for v in rep9["violations"]}, \
        rep9["violations"]
    _mark(marks, "整段许可证全文写在元数据里（实测 numpy / multimethod / reportlab / cadquery "
                 "四家这么写）时，ids 只留标识符；台账裁 `BSD-3-Clause` 而 classifier 只给粗名 "
                 "`BSD License` ⇒ 按同族覆盖放过，换成 MIT（真换族）⇒ 仍判「该撤」"
                 "（清洗前这种包挂上裁定条目也永远红）")
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
