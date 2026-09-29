#!/usr/bin/env python3
r"""取证脚本根路径名册：生成 + 对账（第 96 片）。

问的是两件**事实**，由本脚本现扫 `docs/audit/**.py`：
  · 这个文件有没有把**本仓库内部的绝对路径**写成字面量（⇒ 换机/换目录就指错树）；
  · 它有没有指向**仓库外**的绝对字面量（工作区同级 `tmp/` 这类当轮暂存件）。

第一件是判据：要么用 `Path(__file__)` 推根（就什么也不登记），要么由点名规则唯一接住
并登记进 `docs/audit/FORENSIC_ROOT_REGISTER.json`。第二件**只报不红**——那些路径本身就是
那一轮读数的来处，改不成仓库相对。

三档退码：`0` 干净 / `3` 或 `4` 有缺陷 / `2` 前提不成立（名册读不到或一个 `.py` 都扫不着）。

点名规则**按文件名形状**匹配，这一条本身就是本尺的已知弱点（见常驻用例
`test_a_name_shape_rule_can_mis_bucket_a_file`）：`s84/after_battery84.py` 曾因
`battery\d+\.py$` 没有左边界而被当成变异电池豁免掉。所以规则一律带 `/` 左边界，
且 `--emit` 与 `audit()` 两处都要求**恰好一条**接住：
命中 0 条（新写的脚本没归类）或 ≥2 条（两条规则抢同一个文件）⇒ 一个字都不写、退 3，
而不是静默归进兜底档 —— 本尺没有兜底档。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SELF_REL = "docs/audit/s96/build_forensic_root_register.py"
REL = "docs/audit/FORENSIC_ROOT_REGISTER.json"

# 判据侧不许假设本机挂载根：任何**带引号的绝对路径字面量**都算，是否"仓库内"由 resolve 判。
# 字符类不许用 ASCII 白名单：本仓路径含中文（`AI全链路自研`），白名单会把**全部**原告漏掉
# 而只报"零个脚本写死路径"——第 90 片已经在别的尺子上踩过同一格，这次是第二次。
ABS_RE = re.compile(r"""["'](/[^\s"'`\\]{3,})["']""")
# 报告侧只收真像文件系统根的那种（URL 路由 `"/api/v1"` 之类不进读数，避免噪声冒充原告）
HOST_RE = re.compile(r"^/(?:Volumes|Users|home|tmp|private/tmp|mnt|opt)/")
# shell 的赋值右侧是**裸路径**（`R=/Volumes/…`），没有引号可锚：只用引号分支时，17 个 `.sh`
# 里带仓库内绝对路径的 16 个**一个都读不到**（第 99 片现读：引号分支 0 个文件、两分支 16 个）。
# 测量换一种写法就换一个读数 ⇒ 这条分支与它的反例用例一起入库。
SHELL_ABS_RE = re.compile(r"""(?:^|[\s=(])(/[^\s"'`\\)$]{4,})""", re.M)
# 行首注释（`.sh` 的 `# …` 与 `.py` 的 `# …`）里的路径**不算原告**：第 101 片实测——
# 分支不加这道门时，`# W=/Volumes/…` 这种纯说明行会被读成"这个脚本写死了仓库内路径"，
# 于是名册要么多一条不做事的豁免、要么作者被推着把它登记进去（判据在教人记噪声）。
# 只按"行首"判：`R=/x  # 说明` 那种代码 + 尾注释仍然是原告（同一正臂在 `--self-test` 里）。
# 已知让渡：heredoc 体里的 `#` 在 shell 语义上是正文而不是注释，这道门会把它读成注释。
# 本表按文本判行首，分不出"注释"与"heredoc 里的 #",这是收窄换来的一条让渡；
# 第 101 片现算：全语料 `comment_skipped` 合计 0 条（该合计把 heredoc 体一起算在内），
# 所以今天没有任何原告被这道门带走。日后若出现"挡掉 N 条"且 N>0，必须逐条读原文再判。
COMMENT_LINE_RE = re.compile(r"^\s*#")

# (规则名, 文件名判据, 这一类的理由)
BY_DESIGN: list[tuple[str, str, str]] = [
    ("battery", r"/battery\d+\.py$",
     "变异电池按设计就地改**靶文件**（写回后按 sha 复原），仓库绝对路径是它的作业方式；"
     "改成仓库相对会让它去改别的树"),
    ("terminal", r"/terminal\d+\.py$",
     "终局读数脚本：它写的是**那一代收口时**的盘外暂存区与 worktree 路径，"
     "那些路径本身就是历史记录的一部分"),
    ("closeout", r"/closeout\d+[a-z]*\.(?:py|sh)$",
     "收口链脚本按配方要求用绝对路径拼仓库根与 worktree（见项目配方「worktree 必须写绝对路径」"
     "那条）；`.sh` 走这一条，因为它的 `R=` 必须指本次要认证的那棵树"),
]


def _scan(text: str, shell: bool = False) -> tuple[list[tuple[int, str]], int]:
    """返回 ([(行号, 字面量)], 被行首注释门挡掉的条数)。

    引号分支只认引号包住的整串；`shell=True` 时两条分支并跑——`R=/Volumes/…` 没有引号可锚，
    只用引号分支会把整个 `.sh` 面读成空（第一版普查就是这么把 17 读成 1 的）。
    两条分支都过同一道行首注释门：挡掉的条数**进读数**（`comment_skipped`），
    不收进原告集合——"看不见"与"看见了但不算"必须能分开，否则收窄判据等于换一把更盲的尺。
    """
    lines = text.splitlines()
    out: list[tuple[int, str]] = []
    skipped = 0
    raw = [(text.count("\n", 0, m.start()) + 1, m.group(1)) for m in ABS_RE.finditer(text)]
    if shell:
        for m in SHELL_ABS_RE.finditer(text):
            item = (text.count("\n", 0, m.start(1)) + 1, m.group(1))
            if item not in raw:
                raw.append(item)
    for ln, lit in sorted(raw):
        src = lines[ln - 1] if 1 <= ln <= len(lines) else ""
        if COMMENT_LINE_RE.match(src):
            skipped += 1
            continue
        out.append((ln, lit))
    return out, skipped


def literals(text: str, shell: bool = False) -> list[tuple[int, str]]:
    """`_scan` 的原告侧：行首注释里的路径不在返回值里。"""
    return _scan(text, shell)[0]


def repo_inside(root: Path, lit: str) -> bool:
    try:
        resolved = Path(lit).resolve()
    except OSError:                                    # pragma: no cover
        return False
    return resolved == root or root in resolved.parents


def repo_roots(tree: Path) -> list[Path]:
    """同一座仓库有几个合法落点：主工作树 + 每一个 `git worktree` 签出。

    "仓库内"必须按**仓库身份**判，不能按这一次签出的目录前缀判。第 96 片的认证那一跑
    就是在 `.wt-s96` 里跑的：按前缀判时 50 个原告全部读成 0（于是名册那 50 条同时
    全判「该撤」），而它们指的确实是同一座仓库的主工作树。
    """
    roots = [tree]
    try:
        out = subprocess.run(["git", "-C", str(tree), "worktree", "list", "--porcelain"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return roots                      # git 不在场（合成语料、无 .git 的镜像）：只认这棵树
    if out.returncode != 0:
        return roots
    for ln in out.stdout.splitlines():
        if ln.startswith("worktree "):
            p = Path(ln[len("worktree "):].strip()).resolve()
            if p != tree:
                roots.append(p)
    return roots


def facts(root: Path) -> list[dict]:
    """每个取证脚本（`.py` 与 `.sh`）一条读数；本脚本自己不算（模式串里就带着被判的字面量）。"""
    root = Path(root).resolve()
    roots = [root] + [r for r in repo_roots(root) if r != root]
    rows: list[dict] = []
    files = [f for f in sorted((root / "docs" / "audit").rglob("*"))
             if f.suffix in (".py", ".sh") and f.is_file()]
    for f in files:
        rel = f.relative_to(root).as_posix()
        if rel == SELF_REL:
            continue
        shell = f.suffix == ".sh"
        text = f.read_text(encoding="utf-8", errors="replace")
        lits, skipped = _scan(text, shell=shell)
        inside = [(ln, lit) for ln, lit in lits if any(repo_inside(r, lit) for r in roots)]
        ins = set(inside)
        rows.append({
            "path": rel,
            "shell": shell,
            "comment_skipped": skipped,
            "inside": inside,
            "outside": [(ln, lit) for ln, lit in lits
                        if (ln, lit) not in ins and HOST_RE.match(lit)],
            "tempfile": bool(re.search(r"tempfile\.(mkdtemp|mkstemp|NamedTemporaryFile|"
                                       r"TemporaryDirectory|gettempdir)", text)),
            "rules": [n for n, pat, _w in BY_DESIGN if re.search(pat, rel)],
        })
    return rows


def load_register(root: Path) -> tuple[dict[str, dict], list[str]]:
    p = root / REL
    if not p.is_file():
        return {}, [f"register_missing: 读不到 {REL}"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"register_unparsable: {exc}"]
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {}, [f"register_shape: {REL} 里没有 entries 数组"]
    reg: dict[str, dict] = {}
    problems: list[str] = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("path"), str):
            problems.append(f"register_entry: 条目形状不是带 path 的对象：{e!r}")
            continue
        if e["path"] in reg:
            problems.append(f"register_duplicate: {e['path']} 登记了两遍")
            continue
        reg[e["path"]] = e
    return reg, problems


def audit(root: Path) -> dict:
    reg, problems = load_register(root)
    rows = facts(root)
    by_path = {r["path"]: r for r in rows}
    violations: list[dict] = []
    buckets = {"exempt": 0, "derived": 0, "unwatched": 0}
    for r in rows:
        if not r["inside"]:
            if r["path"] in reg:
                violations.append({
                    "field": "名册该撤", "doc": r["path"], "line": 0,
                    "written": r["path"],
                    "detail": "登记说这个文件写死了仓库内绝对路径，但现扫它已经不带这种字面量"
                              "⇒ 撤条目，否则名册会攒出一批不做事的豁免"})
            else:
                buckets["derived"] += 1
            continue
        if not r["rules"]:
            buckets["unwatched"] += 1
            violations.append({
                "field": "根路径未点名", "doc": r["path"], "line": r["inside"][0][0],
                "written": r["path"],
                "detail": f"现读它把仓库内绝对路径写死成 {r['inside'][0][1]!r}，"
                          "而没有任何点名规则接住它 ⇒ 换机/换目录它就会指错树："
                          "要么改成 Path(__file__).resolve() 推根，要么给它立一条**唯一**的规则"})
            continue
        if len(r["rules"]) > 1:
            buckets["unwatched"] += 1
            violations.append({
                "field": "点名规则不唯一", "doc": r["path"], "line": r["inside"][0][0],
                "written": ", ".join(r["rules"]),
                "detail": "两条以上点名规则抢同一个文件 ⇒ 豁免理由不唯一，"
                          "这类归属重叠必须先拆开规则，别靠顺序挑第一条"})
            continue
        ent = reg.get(r["path"])
        if ent is None:
            buckets["unwatched"] += 1
            violations.append({
                "field": "名册缺条目", "doc": r["path"], "line": r["inside"][0][0],
                "written": r["path"],
                "detail": f"规则 {r['rules'][0]!r} 接住了它，但名册里没有这一条 ⇒ "
                          "豁免没有落到纸面（跑一次 --emit 补登记）"})
            continue
        if ent.get("rule") != r["rules"][0]:
            buckets["unwatched"] += 1
            violations.append({
                "field": "名册规则过期", "doc": REL, "line": 0, "written": r["path"],
                "detail": f"登记写的是 rule={ent.get('rule')!r}，现按规则表算出来是 "
                          f"{r['rules'][0]!r} ⇒ 名册与规则表不同源"})
            continue
        if not str(ent.get("reason") or "").strip():
            buckets["unwatched"] += 1
            violations.append({
                "field": "豁免理由空缺", "doc": REL, "line": 0, "written": r["path"],
                "detail": "豁免必须写明为什么绝对路径在这一类脚本里是设计使然；"
                          "没有理由的豁免就是本尺的洞"})
            continue
        buckets["exempt"] += 1
    for rel in sorted(set(reg) - set(by_path)):
        violations.append({
            "field": "名册该撤", "doc": REL, "line": 0, "written": rel,
            "detail": "登记里有这一条，但磁盘上已经没有这个 `.py` ⇒ 撤条目"})
    outside = [{"path": r["path"], "lits": [lit for _ln, lit in r["outside"]]}
               for r in rows if r["outside"]]
    if not rows:
        problems.append("corpus_empty: docs/audit 下一个 .py/.sh 都没扫到")
    ok = not violations and not problems
    n_py = sum(1 for r in rows if not r["shell"])
    return {"ok": ok, "buckets": buckets,
            "corpus": {"py_files": n_py, "sh_files": len(rows) - n_py,
                       "script_files": len(rows), "register_size": len(reg),
                       "inside_hardcoded": sum(1 for r in rows if r["inside"]),
                       "outside_hardcoded": len(outside),
                       "uses_tempfile": sum(1 for r in rows if r["tempfile"]),
                       "comment_skipped": sum(r["comment_skipped"] for r in rows)},
            "outside": outside, "violations": violations, "problems": problems}


def emit(root: Path) -> int:
    rows = [r for r in facts(root) if r["inside"]]
    bad = [r["path"] for r in rows if len(r["rules"]) != 1]
    if bad:
        print(f"以下文件的点名规则命中数不是 1 ⇒ 一个字都不写：{bad}")
        return 3
    entries = [{"path": r["path"], "rule": r["rules"][0], "hardcoded": True,
                "line": r["inside"][0][0],
                "reason": next(w for n, _p, w in BY_DESIGN if n == r["rules"][0])}
               for r in rows]
    out = root / REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"entries": entries}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"已写 {REL}：{len(entries)} 条豁免（{len(rows)} 个文件写死仓库内绝对路径）")
    return 0


def render(rep: dict) -> str:
    c = rep["corpus"]
    b = rep["buckets"]
    lines = ["=" * 60, "取证脚本根路径对账", "=" * 60,
             f"取证脚本 {c['script_files']} 个（.py {c['py_files']} / .sh {c['sh_files']}；"
             f"写死仓库内 {c['inside_hardcoded']}、写死仓库外 {c['outside_hardcoded']}、"
             f"用 tempfile {c['uses_tempfile']}、行首注释挡掉 {c['comment_skipped']} 条），"
             f"名册 {c['register_size']} 条",
             f"归属：已豁免 {b['exempt']} / 按 __file__ 推根 {b['derived']}"
             f" / 无人守 {b['unwatched']}"]
    for v in rep["violations"]:
        lines.append(f"  ✗ {v['field']} {v['doc']}:{v['line']} `{v['written']}` ⇒ {v['detail']}")
    for p in rep["problems"]:
        lines.append(f"  ! 前提不成立：{p}")
    if rep["ok"]:
        lines.append("现状面缺陷 0 条：每个写死仓库路径的取证脚本都有唯一一条写明了理由的豁免")
    lines.append(f"只报不红（仓库外绝对字面量 {c['outside_hardcoded']} 个文件）："
                 + "、".join(o["path"] for o in rep["outside"][:3])
                 + ("…" if len(rep["outside"]) > 3 else ""))
    return "\n".join(lines)


def _mark(marks: list[str], text: str) -> None:
    print(f"✓立住 {text}")
    marks.append(text)


def _write(tmp: Path, rel: str, text: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _mk(tmp: Path) -> tuple[str, str]:
    """`inside` 由 tmp 现算（写死本机路径会让所有臂都落在仓库外）；
    `outside` 用 `/tmp/…`：它必须命中 HOST_RE 才不会落进读数，又不可能在任何仓库内。"""
    return str(tmp / "repo"), "/tmp/s96_scratch"


def _clean(tmp: Path) -> None:
    """重置成只含「电池豁免 + 推根脚本」的干净树。

    必须整片重建：上一支臂注入的 `s2/terminal2.py` 之类不会自己消失，
    留着它后面每支臂读到的都是别人的原告（第 96 片自测第一轮就是这么红的）。
    """
    shutil.rmtree(tmp / "docs" / "audit", ignore_errors=True)
    inside, _out = _mk(tmp)
    _write(tmp, "docs/audit/s1/battery1.py", f'REPO = Path("{inside}")\n')
    _write(tmp, "docs/audit/s1/probe1.py", "REPO = Path(__file__).resolve().parents[3]\n")
    _write(tmp, REL, json.dumps({"entries": [{
        "path": "docs/audit/s1/battery1.py", "rule": "battery", "hardcoded": True,
        "line": 1, "reason": "合成：电池就地改靶文件"}]}, ensure_ascii=False))


def _self_test(tmp: Path) -> int:
    marks: list[str] = []
    hard = tmp / "hard"
    inside, outside = _mk(hard)
    _clean(hard)
    rep = audit(hard)
    assert not rep["violations"], rep["violations"]
    assert rep["buckets"] == {"exempt": 1, "derived": 1, "unwatched": 0}, rep["buckets"]
    _mark(marks, "对照组：电池豁免接住一条、__file__ 推根那条不登记 ⇒ 零红")

    _write(hard, "docs/audit/s2/extra.py", f'R = Path("{inside}/extra")\n')
    rep2 = audit(hard)
    fired = {(v["field"], v["doc"]) for v in rep2["violations"]}
    assert ("根路径未点名", "docs/audit/s2/extra.py") in fired, fired
    assert rep2["buckets"]["unwatched"] == 1, rep2["buckets"]
    _mark(marks, "「未点名」开火：新写的取证脚本把仓库内路径写死而没归类 ⇒ 判红，"
                 "而不是静默进册或静默漏网")

    (hard / "docs/audit/s2/extra.py").unlink()
    rep3 = audit(hard)
    assert not rep3["violations"], rep3["violations"]
    _mark(marks, "撤掉注入文件后同一棵树复归零红 ⇒ 上面那笔确实是原告，不是名册噪声")

    _write(hard, "docs/audit/s1/battery1.py", "R = Path.home()\n")
    rep4 = audit(hard)
    fired4 = {(v["field"], v["doc"]) for v in rep4["violations"]}
    assert ("名册该撤", "docs/audit/s1/battery1.py") in fired4, fired4
    _mark(marks, "「该撤」第一极：脚本改成推根之后名册仍挂着它 ⇒ 判红（不做事的豁免）")

    _clean(hard)
    _write(hard, "docs/audit/s2/terminal2.py", f'R = Path("{inside}")\n')
    rep5 = audit(hard)
    fired5 = {(v["field"], v["doc"]) for v in rep5["violations"]}
    assert ("名册缺条目", "docs/audit/s2/terminal2.py") in fired5, fired5
    _mark(marks, "「缺条目」开火：规则表接住了但名册里没有这一条 ⇒ 判红，豁免要落到纸面")

    _clean(hard)
    _write(hard, "docs/audit/s2/terminal2.py", f'R = Path("{inside}")\n')
    reg = json.loads((hard / REL).read_text(encoding="utf-8"))
    reg["entries"].append({"path": "docs/audit/s2/terminal2.py", "rule": "terminal",
                           "hardcoded": True, "line": 1, "reason": "   "})
    _write(hard, REL, json.dumps(reg, ensure_ascii=False))
    rep6 = audit(hard)
    fired6 = {(v["field"], v["written"]) for v in rep6["violations"]}
    assert ("豁免理由空缺", "docs/audit/s2/terminal2.py") in fired6, fired6
    _mark(marks, "「理由空缺」开火：理由只有空白也算没理由（不能靠空串换免跑）")

    _clean(hard)
    reg = json.loads((hard / REL).read_text(encoding="utf-8"))
    reg["entries"].append({"path": "docs/audit/s9/gone.py", "rule": "battery",
                           "hardcoded": True, "line": 1, "reason": "合成"})
    _write(hard, REL, json.dumps(reg, ensure_ascii=False))
    rep7 = audit(hard)
    fired7 = {(v["field"], v["written"]) for v in rep7["violations"]}
    assert ("名册该撤", "docs/audit/s9/gone.py") in fired7, fired7
    _mark(marks, "「该撤」第二极：登记的 `.py` 已经从磁盘上没了 ⇒ 判红")

    _clean(hard)
    _write(hard, "docs/audit/s1/battery1.py",
           f'R = Path("{inside}")\nT = Path("{outside}/s1")\n')
    rep8 = audit(hard)
    assert not rep8["violations"], rep8["violations"]
    assert rep8["corpus"]["outside_hardcoded"] == 1, rep8["corpus"]
    assert rep8["outside"][0]["lits"] == [f"{outside}/s1"], rep8["outside"]
    _mark(marks, "「只报不红」那一档：仓库外的绝对字面量进读数、不进判据"
                 "（那些路径本身就是当轮历史的来处）")

    _clean(hard)
    _write(hard, "docs/audit/after_battery1.py", f'R = Path("{inside}")\n')
    rep9 = audit(hard)
    fired9 = {(v["field"], v["doc"]) for v in rep9["violations"]}
    assert ("根路径未点名", "docs/audit/after_battery1.py") in fired9, fired9
    _mark(marks, "形状猜的代价（本尺已知弱点）：`after_battery1.py` 不是电池，"
                 "`/battery\\d+\\.py$` 带左边界之后不接它 ⇒ 判红而不是被豁免吞掉")

    _clean(hard)
    reg = json.loads((hard / REL).read_text(encoding="utf-8"))
    reg["entries"][0]["rule"] = "terminal"
    _write(hard, REL, json.dumps(reg, ensure_ascii=False))
    rep10 = audit(hard)
    fired10 = {(v["field"], v["written"]) for v in rep10["violations"]}
    assert ("名册规则过期", "docs/audit/s1/battery1.py") in fired10, fired10
    _mark(marks, "「规则过期」开火：名册记的 rule 与现按规则表算出来的不是同一条 ⇒ 判红")

    assert emit(hard) == 0
    rep11 = audit(hard)
    assert rep11["ok"], rep11["violations"]
    _mark(marks, "--emit 之后名册与规则表同源（生成侧与判据侧读的是同一把 facts()）")

    _write(hard, "docs/audit/s3/ambiguous.py", f'R = Path("{inside}")\n')
    assert emit(hard) == 3
    rep12 = audit(hard)
    fired12 = {(v["field"], v["doc"]) for v in rep12["violations"]}
    assert ("根路径未点名", "docs/audit/s3/ambiguous.py") in fired12, fired12
    _mark(marks, "命中 0 条那一极：没归类的脚本让 --emit 整批拒写（退 3），"
                 "判据侧同一条按未点名开火")

    (hard / "docs/audit/s3/ambiguous.py").unlink()
    BY_DESIGN.append(("overlap", r"\.py$", "合成：故意与三条点名规则全都重叠"))
    try:
        rep13 = audit(hard)
        fired13 = {(v["field"], v["doc"]) for v in rep13["violations"]}
        assert ("点名规则不唯一", "docs/audit/s1/battery1.py") in fired13, fired13
        assert emit(hard) == 3
    finally:
        BY_DESIGN.pop()
    assert audit(hard)["ok"], "复位规则表之后同一棵树应复归零红"
    _mark(marks, "命中 ≥2 条那一极（结构上要注入一条重叠规则才到得了）：判据报"
                 "「点名规则不唯一」且 --emit 拒写 ⇒ 这条闸不是写给人看的摆设")

    _clean(hard)
    reg = json.loads((hard / REL).read_text(encoding="utf-8"))
    reg["entries"].append(dict(reg["entries"][0]))
    reg["entries"][-1]["reason"] = "合成：同一个文件登记两遍，第二遍换了理由"
    _write(hard, REL, json.dumps(reg, ensure_ascii=False))
    rep14 = audit(hard)
    assert any(x.startswith("register_duplicate") for x in rep14["problems"]), rep14["problems"]
    assert main(["--repo", str(hard)]) == 2, main(["--repo", str(hard)])
    _mark(marks, "「名册重复」开火：同一路径登记两遍 ⇒ 算前提塌（退 2）而不是默默取其中一份"
                 "——两条臂各自的理由都还在，取哪一份都不该由遍历顺序决定")

    _clean(hard)
    _write(hard, "docs/audit/s2/other.sh", f'R = {inside}/extra\necho "$R"\n')
    rep15 = audit(hard)
    fired15 = {(v["field"], v["written"]) for v in rep15["violations"]}
    assert ("根路径未点名", "docs/audit/s2/other.sh") in fired15, fired15
    _mark(marks, "「.sh 也在分母里」：shell 赋值右侧的裸绝对路径（`R=/…`，没有引号可锚）"
                 "被认成仓库内字面量并判红——只用引号分支时整个 .sh 面读成空")

    _clean(hard)
    _write(hard, "docs/audit/s2/both.sh",
           f'R = {inside}/bare\nQ = "{inside}/quoted"\n')
    row = next(r for r in facts(hard) if r["path"] == "docs/audit/s2/both.sh")
    got = {lit for _n, lit in row["inside"]}
    assert got == {f"{inside}/bare", f"{inside}/quoted"}, (got, row)
    py_only = literals((hard / "docs/audit/s2/both.sh").read_text(encoding="utf-8"))
    assert [lit for _n, lit in py_only] == [f"{inside}/quoted"], py_only
    _mark(marks, "两种书写形态各读到一次：裸赋值与带引号赋值都在 `shell=True` 里出现，"
                 "而只用引号分支（`shell=False`）恰好漏掉裸的那一条 ⇒ "
                 "「测量换写法就换读数」这一格由这条断言钉住")

    _clean(hard)
    _write(hard, "docs/audit/s2/commented.sh",
           f'# W = {inside}/只在注释里\nR = {inside}/代码里\nS = {inside}/尾注释  # 说明\n')
    rowc = next(r for r in facts(hard) if r["path"] == "docs/audit/s2/commented.sh")
    gotc = {lit for _n, lit in rowc["inside"]}
    assert gotc == {f"{inside}/代码里", f"{inside}/尾注释"}, (gotc, rowc)
    assert rowc["comment_skipped"] == 1, rowc
    _write(hard, "docs/audit/s2/commented.py",
           f'# q = "{inside}/只在注释里"\np = "{inside}/代码里"\n')
    rowp = next(r for r in facts(hard) if r["path"] == "docs/audit/s2/commented.py")
    gotp = {lit for _n, lit in rowp["inside"]}
    assert gotp == {f"{inside}/代码里"}, (gotp, rowp)
    assert rowp["comment_skipped"] == 1, rowp
    assert audit(hard)["corpus"]["comment_skipped"] == 2, audit(hard)["corpus"]
    assert "行首注释挡掉 2 条" in render(audit(hard)), render(audit(hard)).splitlines()[2]
    _mark(marks, "行首注释不算原告，但**只按行首判**：shell 面三行里行首注释那条被挡并计入"
                 "`comment_skipped`，`R=…` 与「代码 + 尾注释」两条仍是原告；py 面带引号的注释行同样被挡"
                 "（挡掉的条数既进 `corpus` 聚合、也进那行自报，所以这道门不会把判据变成一把更盲的尺）")

    _clean(hard)
    _write(hard, "docs/audit/closeout99.sh", f'R = {inside}\n')
    assert emit(hard) == 0
    reg99 = load_register(hard)[0]
    ent = reg99.get("docs/audit/closeout99.sh")
    assert ent and ent["rule"] == "closeout", reg99
    assert audit(hard)["ok"], audit(hard)["violations"]
    _mark(marks, "`.sh` 走 `closeout` 那条点名规则：命名成 closeoutNN.sh 的收口脚本"
                 "被唯一一条写明理由的豁免接住，且 --emit 会把它写进名册")

    empty = tmp / "empty"
    (empty / "docs" / "audit").mkdir(parents=True)
    rep0 = audit(empty)
    assert any(p.startswith("register_missing") for p in rep0["problems"]), rep0["problems"]
    assert main(["--repo", str(empty)]) == 2, main(["--repo", str(empty)])
    _mark(marks, "前提塌：读不到名册 ⇒ 退 2（不许把「一个都没扫到」读成「零风险」）")

    print(f"---- 合成语料上 {len(marks)} 条判据读数全部对上 ----")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    if "--emit" in argv:
        i = argv.index("--repo") + 1 if "--repo" in argv else None
        return emit(Path(argv[i]) if i is not None else Path(__file__).resolve().parents[3])
    i = argv.index("--repo") + 1 if "--repo" in argv else None
    root = Path(argv[i]) if i is not None else Path(__file__).resolve().parents[3]
    rep = audit(root)
    print(render(rep))
    if rep["problems"]:
        return 2
    return 0 if rep["ok"] else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
