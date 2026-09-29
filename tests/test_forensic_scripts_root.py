r"""取证脚本根路径门禁的常驻牙（F-FORENSIC-ROOT 第 96 片）。

分五组：① 量具必须被真的 spawn；② 真仓库上分母非空、档位求和 == 分母、退码由判据自己定；
③ "零命中"这一格必须是现算的零（把同一把尺子架在故意坏掉的树上要开火）；
④ 只报不红那一档在真语料上确实有原告（否则它是空档）；⑤ 形状猜规则的已知弱点钉住。
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "docs" / "audit" / "s96" / "build_forensic_root_register.py"
REGISTER = ROOT / "docs" / "audit" / "FORENSIC_ROOT_REGISTER.json"


def _mod() -> ModuleType:
    """**从源码文本现编译**，不走 `importlib` 的字节码缓存。

    本机 `sys.pycache_prefix` 指向 `~/Library/Caches/com.apple.python`（macOS 默认），
    而缓存有效性只看 (源 mtime 的整秒, 源字节数)。第 96 片实测：变异电池把
    `buckets["derived"] += 1` 改成 `+= 0`（**同长度**）之后 `py_compile` 落了缓存，
    还原源文件落在同一秒 ⇒ 缓存被判"仍然有效"，之后每一次 import 跑的都是变异体。
    """
    code = compile(TOOL.read_text(encoding="utf-8"), str(TOOL), "exec")
    m = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("bfr96", loader=None))
    m.__file__ = str(TOOL)
    exec(code, m.__dict__)
    return m


bfr = _mod()


def _spawn(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=300)


def _lit(tmp: Path, sub: str) -> str:
    """由 json.dumps 生成 `Path("…")` 那一段：f-string 里嵌同族引号在 py3.9 会吃掉尾引号。"""
    return f"Path({json.dumps(str(tmp / sub))})"


def _write(tmp: Path, rel: str, text: str) -> None:
    """注入的夹具必须是合法 Python——半拉引号的注入只会读出"尺子没牙"这个假象。"""
    ast.parse(text)
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _clean_tree(tmp: Path) -> Path:
    """一棵只含「电池豁免 + 推根脚本」的树，两极都从它出发。"""
    hard = tmp / "hard"
    inside = str(hard / "repo")
    _write(hard, "docs/audit/s1/battery1.py", f'REPO = Path("{inside}")\n')
    _write(hard, "docs/audit/s1/probe1.py", "REPO = Path(__file__).resolve().parents[3]\n")
    _write(hard, bfr.REL, json.dumps({"entries": [{
        "path": "docs/audit/s1/battery1.py", "rule": "battery", "hardcoded": True,
        "line": 1, "reason": "合成：电池就地改靶文件"}]}, ensure_ascii=False))
    return hard


def test_instrument_self_test_is_actually_spawned_and_green() -> None:
    """没有这一条，`--self-test` 与"没有自测"在读数上不可区分（第 60 片的孤儿门禁）。"""
    proc = _spawn("--self-test")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条判据读数全部对上" in proc.stdout, proc.stdout
    marks = proc.stdout.count("✓立住")
    assert marks >= 15, f"--self-test 的臂从 15 条缩水成 {marks} 条：注入没跑满就别谈判据"


def test_real_repo_face_is_live_and_return_code_follows_the_verdict() -> None:
    rep = bfr.audit(ROOT)
    c = rep["corpus"]
    assert not rep["problems"], rep["problems"]
    assert not rep["violations"], rep["violations"]
    assert c["py_files"] > 40, c
    # 档位求和 == 分母：漏一档或重一档都会在这里翻，而不是靠记住某个数
    b = rep["buckets"]
    assert b["exempt"] + b["derived"] + b["unwatched"] == c["py_files"], (b, c)
    assert b["exempt"] == c["inside_hardcoded"], (b, c)
    assert b["exempt"] > 30, b
    assert b["derived"] > 5, b
    assert c["register_size"] == c["inside_hardcoded"], c
    rc = _spawn("--repo", str(ROOT)).returncode
    assert rc == (0 if rep["ok"] else 4), (rc, rep["ok"])


def test_the_abs_probe_reaches_a_non_ascii_repo_path() -> None:
    """真仓库根含中文（`AI全链路自研`）⇒ ASCII 白名单字符类会**静默漏掉全部原告**。

    这一条钉的是识别面：把本机真根当字面量塞进夹具，尺子必须认它是"仓库内"。
    少了这一条，`写死仓库内 0` 这种读数与"真的没人写死"在终端上完全同形。
    """
    assert not str(ROOT).isascii(), "本条的前提是仓库根含非 ASCII，改成纯 ASCII 路径就该换探针"
    hits = bfr.literals(f'R = Path("{ROOT}")\n')
    assert [lit for _n, lit in hits] == [str(ROOT)], hits
    assert bfr.repo_inside(ROOT, str(ROOT)), "resolve 之后必须判成仓库内"
    assert bfr.audit(ROOT)["corpus"]["inside_hardcoded"] > 0, bfr.audit(ROOT)["corpus"]


def test_an_unlisted_script_fires_and_the_listed_one_does_not(tmp_path: Path) -> None:
    """两极：点名过的豁免不开火；同样写死但没归类的一开火就点名它。"""
    hard = _clean_tree(tmp_path)
    rep = bfr.audit(hard)
    assert not rep["violations"], rep["violations"]
    assert rep["buckets"]["exempt"] == 1, rep["buckets"]

    _write(hard, "docs/audit/s2/newprobe.py", f"R = {_lit(hard, 'src')}\n")
    rep2 = bfr.audit(hard)
    fired = {(v["field"], v["written"]) for v in rep2["violations"]}
    assert ("根路径未点名", "docs/audit/s2/newprobe.py") in fired, fired
    assert rep2["buckets"]["unwatched"] == 1, rep2["buckets"]


def test_outside_repo_literals_are_reported_but_never_judge(tmp_path: Path) -> None:
    """只报不红这一档不许是空档：真仓库上它有原告，合成树上它开不了火。"""
    rep = bfr.audit(ROOT)
    assert rep["ok"], rep["violations"]
    assert rep["corpus"]["outside_hardcoded"] > 0, rep["corpus"]
    assert rep["outside"], "真仓库上这一档为空 ⇒ 本条前提塌，别把'没有'当'通过'"

    hard = _clean_tree(tmp_path)
    _write(hard, "docs/audit/s1/battery1.py",
           f"R = {_lit(hard, 'repo')}\nT = Path(\"/tmp/s96_scratch\")\n")
    # URL 路由那类绝对字面量不许混进"仓库外路径"读数：放宽了就与本档的语义不是同一件事
    _write(hard, "docs/audit/s1/apiroute.py", 'ROUTE = "/api/v1/x"\n')
    rep2 = bfr.audit(hard)
    assert not rep2["violations"], rep2["violations"]
    assert rep2["corpus"]["outside_hardcoded"] == 1, rep2["corpus"]
    assert [o["path"] for o in rep2["outside"]] == ["docs/audit/s1/battery1.py"], rep2["outside"]


def test_a_name_shape_rule_can_mis_bucket_a_file(tmp_path: Path) -> None:
    """`s84/after_battery84.py` 曾被 `battery\\d+\\.py$` 当成电池豁免掉——本轮真实踩到。

    规则一律带 `/` 左边界之后，这种名字必须落回"未点名"，而不是被同族词形吞掉。
    """
    hard = _clean_tree(tmp_path)
    _write(hard, "docs/audit/after_battery1.py", f"R = {_lit(hard, 'repo')}\n")
    rep = bfr.audit(hard)
    fired = {(v["field"], v["written"]) for v in rep["violations"]}
    assert ("根路径未点名", "docs/audit/after_battery1.py") in fired, fired
    row = next(f for f in bfr.facts(hard) if f["path"] == "docs/audit/after_battery1.py")
    assert row["rules"] == [], row


def test_premise_missing_register_is_not_zero_risk(tmp_path: Path) -> None:
    """读不到名册 ⇒ 退 2（前提不成立），不许读成"一个都没登记所以零风险"。"""
    empty = tmp_path / "empty"
    (empty / "docs" / "audit").mkdir(parents=True)
    rep = bfr.audit(empty)
    assert any(p.startswith("register_missing") for p in rep["problems"]), rep["problems"]
    assert bfr.main(["--repo", str(empty)]) == 2
    assert rep["ok"] is False


def test_a_duplicated_register_entry_is_a_premise_failure(tmp_path: Path) -> None:
    """同一路径登记两遍 ⇒ 退 2。少这一条，名册里两份互相矛盾的理由会被遍历顺序悄悄选一份。"""
    hard = _clean_tree(tmp_path)
    reg = json.loads((hard / bfr.REL).read_text(encoding="utf-8"))
    reg["entries"].append(dict(reg["entries"][0]))
    reg["entries"][-1]["reason"] = "合成：第二份换了理由"
    _write(hard, bfr.REL, json.dumps(reg, ensure_ascii=False))
    rep = bfr.audit(hard)
    assert any(x.startswith("register_duplicate") for x in rep["problems"]), rep["problems"]
    assert rep["ok"] is False
    assert bfr.main(["--repo", str(hard)]) == 2


def test_register_on_disk_matches_the_rules_table() -> None:
    """名册是生成物：条目集合必须与规则表现算出来的集合逐字相同（防手改名册造豁免）。"""
    reg, problems = bfr.load_register(ROOT)
    assert not problems, problems
    inside = [f["path"] for f in bfr.facts(ROOT) if f["inside"]]
    assert sorted(reg) == sorted(inside), (len(reg), len(inside))
    for rel, ent in reg.items():
        assert str(ent.get("reason", "")).strip(), rel
    # 名册不许出现规则表里没有的档位名（那等于凭空多一类豁免）
    names = {n for n, _p, _w in bfr.BY_DESIGN}
    assert {str(e["rule"]) for e in reg.values()} <= names, {
        str(e["rule"]) for e in reg.values()} - names

