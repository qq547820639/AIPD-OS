r"""`scripts/` 的 lint 面棘轮（F-SCRIPT-LINT 第 100 片）。

问的不是"这条命令今天红不红"，而是**这一面的债有没有只增不减**：CI 的 ruff 门
（`.github/workflows/ci.yml` 那条 `ruff check src tests state_service`）今天不含 `scripts/`，
而 59 个量具脚本都住在那儿（第 99 片现读 642 条命中，落在 44 个文件上）。

形状是**测量基线 + 棘轮**，不是 `per-file-ignores`：
后者会把"同一个文件里新增的同码命中"一起吞掉（豁免是按 文件×规则码 全有全无的），
而要把豁免关掉再量真数，得给 ruff 递一份镜像配置——`--config 'lint.per-file-ignores={...}'`
这种内联写法在 0.16.1 上直接 `error: invalid value`（只接受简单 TOML 键值），
只剩"生成一份复刻 pyproject 的临时配置"那条路，那是把判据的规则集抄第二遍。
所以这里按仓里既有那一族（消费表 / 根路径名册）的做法：**判据只跑真命令、只比自己写的数**。

档位（每个 (文件, 规则码) 格恰好落一档，求和 == 并集行数由常驻用例断）：
  持平 equal / 上涨 rose（判红）/ 未登记 unregistered（判红）/
  已偿 paid（登记 >0 而今天 0 ⇒ 判红：这一行该从基线里撤掉）/ 可下调 shrunk（只报不红）
外加一格直连对账：ci.yml 的 ruff 命令里点名的 `scripts/*.py` 必须**恰好等于**今天 0 债的那批
（多一个 ⇒ 面会当场红；少一个 ⇒ `lint面直连清单落后` 判红，面只许往前走）。

前提塌（退 2，不折算成"零债"）：基线读不到 / 基线解析不出 / 跑不起 ruff /
语料里一个 `.py` 都没有 / ruff 一条命中都没报而基线非空（那是尺子或语料换了，不是债清完了）。

跑法：
    python scripts/scripts_lint_ratchet.py            # 判据（0 绿 / 4 判红 / 2 前提塌）
    python scripts/scripts_lint_ratchet.py --emit     # 重写基线（拒写条件见 emit()）
    python scripts/scripts_lint_ratchet.py --self-test
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASELINE_REL = "docs/audit/SCRIPTS_LINT_BASELINE.json"
CI_REL = ".github/workflows/ci.yml"
FACE_DIR = "scripts"
RUFF_ARG = "scripts"
SELF_REL = "scripts/scripts_lint_ratchet.py"
CONCISE_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+): (?P<code>[A-Z]+\d+) ")


def measure(root: Path) -> tuple[collections.Counter, list[str], list[str]]:
    """跑**真 ruff**（用仓库自己的配置，不镜像规则集），返回 (格 → 命中数, 语料文件, 问题)。"""
    problems: list[str] = []
    files = sorted(p.relative_to(root).as_posix()
                   for p in (root / FACE_DIR).rglob("*.py") if p.is_file())
    if not files:
        problems.append(f"corpus_empty: {FACE_DIR}/ 下一个 .py 都没有")
        return collections.Counter(), files, problems
    proc = subprocess.run([sys.executable, "-m", "ruff", "check", "--no-cache",
                           "--output-format", "concise", RUFF_ARG],
                          cwd=str(root), capture_output=True, text=True, timeout=900)
    if proc.returncode not in (0, 1):
        problems.append(f"ruff_unrunnable: ruff 退出码 {proc.returncode}"
                        f"（0=无命中 1=有命中，其余都是跑不起来）：{(proc.stderr or '')[:160]}")
        return collections.Counter(), files, problems
    hits: collections.Counter = collections.Counter()
    for ln in proc.stdout.splitlines():
        m = CONCISE_RE.match(ln.strip())
        if not m:
            continue
        if m.group("code") == "E902":        # 语法错不是 lint 债，是尺子读不了这一格
            problems.append(f"unparsable: {m.group('file')}:{m.group('line')}")
            continue
        hits[(m.group("file"), m.group("code"))] += 1
    if proc.returncode == 1 and not hits and len(files) > 1:
        # rc=1 说明 ruff 报了东西，而我一行都没解析出来 ⇒ 是尺子瞎了，不是债清完了。
        # rc=0 才是"真清"那一档（债偿完是目标状态，不许当成前提塌来挡）。
        problems.append("zero_hits: ruff 退 1（有命中）而解析出 0 行 ⇒ 输出格式或码名规则变了，"
                        "不把『读不到』折成『零债』")
    return hits, files, problems


def ci_face_files(root: Path) -> list[str]:
    """ci.yml 里 ruff 那条命令**点名**的 scripts 文件（逐字读，不猜）。"""
    p = root / CI_REL
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8")
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("run: ruff check"):
            return sorted(a for a in s[len("run: "):].split()[1:] if a.startswith("scripts/"))
    return []


def load_baseline(root: Path) -> tuple[dict, list[str]]:
    p = root / BASELINE_REL
    problems: list[str] = []
    if not p.is_file():
        return {}, [f"baseline_missing: 读不到 {BASELINE_REL}"]
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"baseline_unreadable: {BASELINE_REL} 解析失败：{exc}"]
    if "entries" not in raw or "files" not in raw:
        return {}, [f"baseline_unreadable: 缺 entries/files 键（实得 {sorted(raw)}）"]
    return raw, problems


def audit(root: Path) -> dict:
    root = Path(root).resolve()
    hits, files, problems = measure(root)
    base, problems2 = load_baseline(root)
    problems += problems2
    if problems:
        return {"ok": False, "problems": problems, "violations": [], "outside": [],
                "buckets": {}, "corpus": {"py_files": len(files), "hits": sum(hits.values())}}
    reg: dict[tuple[str, str], int] = {(e["file"], e["code"]): int(e["count"])
                                       for e in base["entries"]}
    registered_files = set(base["files"])
    viol: list[dict] = []
    buckets: collections.Counter = collections.Counter()
    # 空档也要在场：Counter 里"没有这个键"和"这个键是 0"对读者是两件事，
    # 而下游（常驻用例、--json 的消费者）拿缺键当 0 就会把"没数过"读成"没有"。
    for k in ("equal", "rose", "unregistered", "paid", "shrunk",
              "uncovered", "gone", "face", "rows"):
        buckets[k] += 0
    for key in sorted(set(reg) | set(hits)):
        f, code = key
        today, want = hits.get(key, 0), reg.get(key, 0)
        if want == 0 and today > 0:
            buckets["unregistered"] += 1
            viol.append({"field": "lint面基线缺条目", "file": f, "code": code,
                         "detail": f"今天有 {today} 条 {code}，基线里没有这一格 ⇒ "
                                   "新出现的规则码（或新文件）没人记账，判红而不是默默放行"})
        elif today > want:
            buckets["rose"] += 1
            viol.append({"field": "lint面债上涨", "file": f, "code": code,
                         "detail": f"{f} 的 {code} 从登记的 {want} 涨到 {today} ⇒ 棘轮只许往下"})
        elif want > 0 and today == 0:
            buckets["paid"] += 1
            viol.append({"field": "lint面基线该撤", "file": f, "code": code,
                         "detail": f"{f} 的 {code} 今天 0 命中，基线还留着 {want} ⇒ "
                                   "豁免清单不许只涨不消，重跑 --emit 把它摘掉"})
        elif today < want:
            buckets["shrunk"] += 1
        else:
            buckets["equal"] += 1
    for f in files:
        if f not in registered_files:
            viol.append({"field": "lint面文件未覆盖", "file": f, "code": "-",
                         "detail": f"{f} 在语料里而基线的文件清单没有它 ⇒ 新文件必须记账"
                                   "（哪怕它今天 0 债，也要在 --emit 里露头）"})
            buckets["uncovered"] += 1
    for f in sorted(registered_files - set(files)):
        viol.append({"field": "lint面基线该撤", "file": f, "code": "-",
                     "detail": f"基线登记了 {f}，而它已不在语料里 ⇒ 撤掉，别攒幽灵条目"})
        buckets["gone"] += 1
    face, zero = ci_face_files(root), sorted(f for f in files if not any(k[0] == f for k in hits))
    # 债全偿完那个终态也得走得通：那时逐个点名 59 个文件已无意义，命令该退回整目录。
    face_ok = face == zero or (zero == sorted(files) and RUFF_ARG in face)
    if not face_ok:
        extra = [x for x in face if x not in zero]
        missing = [x for x in zero if x not in face]
        detail = (f"ci.yml 的 ruff 命令点名 {len(face)} 个 scripts 文件，"
                  f"而今天真正 0 债的是 {len(zero)} 个；"
                  f"多点的 {extra} 会让 CI 当场红，"
                  f"漏点的 {missing} 说明有人清了债却没把文件接进面")
        viol.append({"field": "lint面直连清单不同源", "file": CI_REL,
                     "code": f"+{len(extra)}/-{len(missing)}", "detail": detail})
        buckets["face"] += 1
    buckets["rows"] = len(set(reg) | set(hits))
    return {"ok": not viol, "problems": problems, "violations": viol,
            "outside": [{"file": f, "code": c, "today": hits.get((f, c), 0),
                         "registered": reg.get((f, c), 0)}
                        for (f, c) in sorted(set(reg) | set(hits))
                        if 0 < hits.get((f, c), 0) < reg.get((f, c), 0)][:20],
            "buckets": dict(buckets),
            "corpus": {"py_files": len(files), "hits": sum(hits.values()),
                       "hit_files": len({f for f, _c in hits}),
                       "zero_files": len(zero), "face_files": len(face),
                       "baseline_rows": len(reg), "codes": len({c for _f, c in hits})}}


def emit(root: Path) -> int:
    root = Path(root).resolve()
    hits, files, problems = measure(root)
    if problems:
        print("前提不成立 ⇒ 整批不落盘：" + "；".join(problems))
        return 2
    entries = [{"file": f, "code": c, "count": n}
               for (f, c), n in sorted(hits.items())]
    zero = sum(1 for f in files if not any(k[0] == f for k in hits))
    out = root / BASELINE_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"entries": entries, "files": files,
                               "totals": {"hits": sum(hits.values()),
                                          "rows": len(entries),
                                          "generated_by": SELF_REL}},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not entries:
        print(f"已写 {BASELINE_REL}：0 格 / {len(files)} 个文件——**全部 0 债**，"
              f"这是债偿完的目标状态，不是尺子失灵（失灵的判据见 measure 的 zero_hits）")
        return 0
    print(f"已写 {BASELINE_REL}：{len(entries)} 格 / {sum(hits.values())} 条命中 / "
          f"{len(files)} 个文件（其中 0 债 {zero} 个）")
    return 0


def render(rep: dict) -> str:
    c = rep["corpus"]
    b = rep.get("buckets", {})
    ln = ["=" * 60, "scripts/ lint 面棘轮对账", "=" * 60]
    if "rows" in b:
        ln.append(f"语料 {c['py_files']} 个 .py（有债 {c['hit_files']} / 0 债 {c['zero_files']}），"
                  f"命中 {c['hits']} 条 / {c['codes']} 个规则码，基线 {c['baseline_rows']} 格，"
                  f"ci.yml 直连 {c['face_files']} 个文件")
        rowsum = sum(b.get(k, 0) for k in ("equal", "rose", "unregistered", "paid", "shrunk"))
        ln.append(f"档位：持平 {b.get('equal', 0)} / 上涨 {b.get('rose', 0)} / "
                  f"未登记 {b.get('unregistered', 0)} / 已偿待撤 {b.get('paid', 0)} / "
                  f"可下调 {b.get('shrunk', 0)}（求和 {rowsum} == 并集 {b.get('rows')}）")
    for v in rep["violations"]:
        ln.append(f"  ✗ {v['field']} {v['file']} `{v['code']}` ⇒ {v['detail']}")
    for o in rep["outside"]:
        ln.append(f"  · 可下调（只报不红）{o['file']} {o['code']}："
                  f"登记 {o['registered']} → 今天 {o['today']}")
    for p in rep["problems"]:
        ln.append(f"  ! 前提不成立：{p}")
    if rep["ok"]:
        ln.append("现状面缺陷 0 条：每一格债都有登记、登记没比现实宽松、直连清单与 0 债集合相等")
    return "\n".join(ln)


def _mkface(root: Path, files: list[str]) -> None:
    (root / CI_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / CI_REL).write_text("jobs:\n  lint:\n    steps:\n      - name: Run ruff\n"
                               "        run: ruff check src tests state_service "
                               + " ".join(files) + "\n", encoding="utf-8")


def _tree(root: Path, files: dict[str, str], face: list[str]) -> Path:
    import shutil
    if root.exists():
        shutil.rmtree(root)
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    _mkface(root, face)
    return root


# 夹具文本按 ruff 的**默认**规则集写（合成树里没有 pyproject）。本轮实测：默认集对
# `a = 1; b = 2` 只报 F841×2，**不报 E702**（E702 要 `--select E702`，或本仓
# `pyproject.toml` 里 `select=["E",…]` 才在场）⇒ 合成臂只按"格与格的关系"断言，
# 不写死码名、不写死条数；生产面用的仍是仓库自己那份配置（`measure()` 不传 --select）。
#   DEBT2 → F841×4；DEBT1 → F841×2；DEBT3 → F841×6；CLEAN → 0 条；IMPORTED → F401×1 + F841×2
DEBT2 = "def f(x):\n    a = 1; b = 2\n    c = 3; d = 4\n    return x\n"
DEBT1 = "def f(x):\n    a = 1; b = 2\n    return x\n"
CLEAN = "def f(x):\n    return x\n"
DEBT3 = "def f(x):\n    a = 1; b = 2\n    c = 3; d = 4\n    e = 5; g = 6\n    return x\n"
HALF = "def f(x):\n    a = 1\n    return x\n"
IMPORTED = "import os\n\n\ndef f(x):\n    a = 1; b = 2\n    return x\n"


BASE = {"scripts/debt.py": DEBT2, "scripts/semi.py": IMPORTED,
        "scripts/third.py": DEBT1, "scripts/clean.py": CLEAN}
FACE = ["scripts/clean.py"]


def _self_test(tmp: Path) -> int:
    marks: list[str] = []

    # ① 合规侧：基线由同一次测量写下 ⇒ 判据必须读成 0 缺陷，且全部格落"持平"
    tree = _tree(tmp / "ok", BASE, FACE)
    assert emit(tree) == 0
    rep = audit(tree)
    b, c = rep["buckets"], rep["corpus"]
    assert rep["ok"], rep["violations"]
    assert b["equal"] == b["rows"] == 4 and c["hits"] == 9, rep
    assert c["zero_files"] == 1 and c["face_files"] == 1, c
    _mark(marks, f"合规侧存在：基线就是这次测量写下的 ⇒ 0 缺陷、四格全落『持平』"
                 f"（rows={b['rows']} hits={c['hits']}）；这条不开火，下面几支的开火才算数")

    # ② 棘轮上涨：已登记的那格多一条同码命中
    t2 = _tree(tmp / "rose", BASE, FACE)
    emit(t2)
    (t2 / "scripts/debt.py").write_text(DEBT3, encoding="utf-8")
    fired = {(v["field"], v["file"]) for v in audit(t2)["violations"]}
    assert fired == {("lint面债上涨", "scripts/debt.py")}, fired
    _mark(marks, "棘轮开火：同一格从登记的 4 涨到 6 就判红——不是『这文件在清单里』就看不见；"
                 "且只红这一格，别档一律不开火")

    # ③ 未登记：文件已有登记，但冒出一个基线里没有的规则码（F841 在、F401 不在）
    t3 = _tree(tmp / "unreg", BASE, FACE)
    emit(t3)
    (t3 / "scripts/third.py").write_text(IMPORTED, encoding="utf-8")
    fired3 = {(v["field"], v["file"], v["code"]) for v in audit(t3)["violations"]}
    assert ("lint面基线缺条目", "scripts/third.py", "F401") in fired3, fired3
    assert ("lint面文件未覆盖", "scripts/third.py") not in fired3, fired3
    _mark(marks, "新规则码露头必须记账：文件在清单里而这一格不在 ⇒ 走『缺条目』而不是被"
                 "当成 0 登记值的『上涨』，没有『这条码没登记所以不判』那第三态")

    # ④ 已偿待撤 + 直连清单落后：三个文件清零 ⇒ 两格同批开火
    t4 = _tree(tmp / "paid", BASE, FACE)
    emit(t4)
    for f in ("debt.py", "semi.py", "third.py"):
        (t4 / "scripts" / f).write_text(CLEAN, encoding="utf-8")
    fired4 = {(v["field"], v["file"]) for v in audit(t4)["violations"]}
    assert ("lint面基线该撤", "scripts/debt.py") in fired4, fired4
    assert ("lint面直连清单不同源", CI_REL) in fired4, fired4
    _mark(marks, "只涨不消那一格：债清零 ⇒ 基线该撤；同时它们变成 0 债文件却没被接进 ci.yml ⇒ "
                 "直连清单不同源。两格同批开火，接面这件事不会被漏掉")

    # ⑤ 可下调：登记比现实宽松、但没到 0 ⇒ 只报不红
    t5 = _tree(tmp / "shrunk", BASE, FACE)
    emit(t5)
    (t5 / "scripts/debt.py").write_text(DEBT1, encoding="utf-8")
    rep5 = audit(t5)
    assert rep5["ok"], rep5["violations"]
    assert rep5["buckets"]["shrunk"] == 1 and rep5["outside"], rep5
    _mark(marks, "现实比登记紧 ⇒ 只报不红，但读数留在桌上（下一轮 --emit 就该把它拧下来）")

    # ⑥ 新文件未覆盖：语料加了文件而基线的文件清单没有它
    t6 = _tree(tmp / "newf", BASE, FACE)
    emit(t6)
    (t6 / "scripts/newcomer.py").write_text(CLEAN, encoding="utf-8")
    fired6 = {(v["field"], v["file"]) for v in audit(t6)["violations"]}
    assert ("lint面文件未覆盖", "scripts/newcomer.py") in fired6, fired6
    _mark(marks, "新文件不许天然站在面外：没进基线文件清单就判红（哪怕它今天 0 债）")

    # ⑦⑧ 前提塌：基线不在 / 一个 .py 都没扫到 ⇒ 退 2，不折成"零债"
    (t6 / BASELINE_REL).unlink()
    assert main(["--repo", str(t6)]) == 2
    _mark(marks, "读不到基线＝前提不成立（退 2），不是『一条债都没有』")
    empty = _tree(tmp / "empty", {}, FACE)
    rep8 = audit(empty)
    assert any(x.startswith("corpus_empty") for x in rep8["problems"]), rep8["problems"]
    assert main(["--repo", str(empty)]) == 2
    assert emit(_tree(tmp / "empty2", {}, [])) == 2, "空语料时 --emit 必须拒写"
    _mark(marks, "语料空＝前提不成立（退 2），`--emit` 同样拒写：空册放行等于把『看不见』"
                 "记成『干净』")

    # ⑨ 档位求和 == 并集行数：一次凑齐五档（equal/rose/paid/shrunk/unregistered）
    t9 = _tree(tmp / "sum", BASE, FACE)
    emit(t9)
    (t9 / "scripts/debt.py").write_text(DEBT3, encoding="utf-8")          # rose 4→6
    (t9 / "scripts/semi.py").write_text(DEBT1, encoding="utf-8")          # paid(F401)+equal(F841)
    (t9 / "scripts/third.py").write_text(HALF, encoding="utf-8")          # shrunk 2→1
    (t9 / "scripts/newcodes.py").write_text(IMPORTED, encoding="utf-8")   # unregistered ×2
    rep9 = audit(t9)
    b9 = rep9["buckets"]
    assert b9["equal"] + b9["rose"] + b9["unregistered"] + b9["paid"] + b9["shrunk"] \
        == b9["rows"], b9
    assert (b9["equal"], b9["rose"], b9["paid"], b9["shrunk"], b9["unregistered"]) \
        == (1, 1, 1, 1, 2), b9
    assert b9["rows"] == 6, b9
    _mark(marks, f"Σ(五档) == 并集行数（{b9}）：五档各落一格、求和正好等于并集 6 行；"
                 "漏一档或重一档都会在这里翻，而不是靠记住某个数")
    print(f"--self-test：{len(marks)} 条合成读数全部对上")
    return 0


def _mark(marks: list, text: str) -> None:
    print(f"✓立住 {text}")
    marks.append(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="scripts/ 的 lint 面棘轮")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)
    if args.self_test:
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    if args.emit:
        return emit(root)
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
