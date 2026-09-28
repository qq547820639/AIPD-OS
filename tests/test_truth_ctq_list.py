"""`aipd ctq list`（F-CTQ-READER 第 62 片）：链头第一个**面向人**的读面。

前提是一条量具测出来的缺席：`record_type="ctq"` 有三个写者（`aipd ctq add` / `ctq revise` /
`ctq deprecate`）和四个读者（发布证据分母、图纸声明输入、出图返工、漂移扫描），
**但没有任何一条命令能让人问出「现在 active 的是哪几条、各自的限值与版本是几」**——
第 60 片那把 `doc_command_census` 把它登记成 registry 里的限制句，
并让「正文点名了一条未注册命令」这件事在只报面上可见（处数一律现算，本文不抄绝对数）。

钉十四组，每组对着一个具体的说谎方式：
1. 命令必须真注册在 argparse 声明树上（派发表里有、parser 里没有就是幻影）；
2. 默认只列 active **必须同时说明排除了几条**——否则「列出 1 条」会被读成「库里只有 1 条」，
   而 `aipd release manifest` 的 `ctq` 数组正是那个形状；
3. 记录投影复用生产面那份 `product_truth.ctq._snapshot`，不在 CLI 里重抄字段
   （`_collect_ctq` 的投影不带 `drawing_feature`，而「这条尺寸归哪条要求管」正是人要看的）；
4. `--json` 的命令标签等于注册名（第 60 片刚修过 `truth ctq add` 那类幻影标签）；
5. 空作用域不许沉默：退 0 + 明写「0 条 + 作用域」，与「没跑到」区分开；
6. 非 active 的其他态（`stale`）在 `--all` 里按库里原样出现，不折进 active 也不折进 superseded；
7. README 速查里有行首可执行那一行——第 60 片那把尺子正判这个；
8. 库文件根本不是 sqlite ⇒ 退 2 且不产出「0 条」（钉 `_open_store` 那一层）；
9. 库打得开而 `list_ctq` 抛在手里 ⇒ 同样退 2（钉命令里那段 try/except；
   8 与 9 分成两条是本轮电池教的——只用 8 那种输入，9 那段代码根本没被执行到）；
10. 读面一行审计都不写，同批用写命令做反向对照证明审计通道本来就通；
11. 合格域**原样**打——`:g` 会把 8.050001 印成 8.05，这条面的存在理由就是把数说准；
12. `total == returned + Σexcluded` 守恒，两种视图各算一遍，`statuses` 跟着视图走；
13. 口径注不许把例外说满（"退出分母的只有 superseded"是错的，实测见该用例）；
14. 两条读失败面带 `--json` 时退 2 且 stdout 上没有 `"ok": true` 的成功件。
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import ProductTruthStore
from aipd_os.product_truth.ctq import _snapshot
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
T = "default"
P = "CTQ-LIST"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant(T)
    state.init_project(T, P, "链头读者面测试", "evidence")
    return db


def _authority_paths() -> set[str]:
    """按 argparse 声明树走一遍，拿到全部「一条命令的完整路径」。"""
    from aipd_os.cli.main import build_parser

    names: set[str] = set()
    stack = [("", build_parser())]
    while stack:
        prefix, parser = stack.pop()
        for action in getattr(parser, "_actions", []):
            choices = getattr(action, "choices", None)
            if not isinstance(choices, dict):
                continue
            for name, sub in choices.items():
                if not hasattr(sub, "_actions"):
                    continue
                path = f"{prefix} {name}".strip()
                names.add(path)
                stack.append((path, sub))
    return names


def _add(db, feature: str, drawing: str, lower: str = "7.95", upper: str = "8.05") -> str:
    rc = main(["ctq", "add", "--db", str(db), "--project", P, "--feature", feature,
               "--drawing-feature", drawing, "--nominal", "8.0", "--lower", lower,
               "--upper", upper, "--inspection", "CMM", "--by", "潘工"])
    assert rc == 0
    return _record_for(db, feature)


def _record_for(db, feature: str) -> str:
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
    return next(str(r.record_id) for r in store.query(record_type="ctq", tenant_id=T,
                                                     project_id=P)
                if (r.metadata or {}).get("feature") == feature)


def _list(db, *extra: str) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["ctq", "list", "--db", str(db), "--project", P, *extra])
    return rc, buf.getvalue()


def _payload(text: str) -> dict:
    # `json.loads` 回的是 Any：CLI 末行打印的是一份 JSON 文档，按文档的真实形状
    # （键为字符串、值由各命令决定）收下，再交给下面的字段断言。
    payload: dict[str, Any] = json.loads(text.strip().splitlines()[-1])
    return payload


def test_ctq_list_is_registered_on_the_argparse_tree(env) -> None:
    db = env
    assert "ctq list" in _authority_paths(), sorted(n for n in _authority_paths()
                                                   if n.startswith("ctq"))
    rc, text = _list(db)
    assert rc == 0, text


def test_default_view_lists_active_and_names_what_it_excluded(env) -> None:
    db = env
    _add(db, "hole_a", "TOP.hole_1")
    keep = _add(db, "hole_b", "TOP.hole_2")
    drop = _add(db, "hole_c", "TOP.hole_3")
    assert main(["ctq", "deprecate", "--db", str(db), "--project", P, "--record", drop,
                 "--reason", "合并到 hole_b", "--by", "潘工"]) == 0

    rc, text = _list(db)
    assert rc == 0, text
    assert "hole_a" in text and "hole_b" in text, text
    assert "hole_c" not in text, text
    assert "另有 1 条未列出" in text and "排除：superseded 1" in text, \
        f"默认视图必须把排除条数与态打出来（不是'1 条'这种要人自己数的读数）：\n{text}"

    rc2, alltext = _list(db, "--all")
    assert rc2 == 0 and "hole_c" in alltext and "superseded" in alltext, alltext
    assert keep in alltext


def test_records_reuse_the_production_projection(env) -> None:
    """读面不许自己重抄字段：生产投影一改，抄的那份就会静默漂开。"""
    db = env
    rid = _add(db, "hole_x", "TOP.hole_9")
    rc, text = _list(db, "--json")
    assert rc == 0, text
    recs = _payload(text)["records"]
    assert [r["record_id"] for r in recs] == [rid], recs
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
    live = [r for r in store.query(record_type="ctq", tenant_id=T, project_id=P)
            if str(r.record_id) == rid]
    assert len(live) == 1
    assert recs[0] == _snapshot(live[0]), \
        f"读面重抄了投影，生产面一改就会漂：\n{recs[0]}\n{_snapshot(live[0])}"
    assert recs[0]["drawing_feature"] == "TOP.hole_9", recs[0]


def test_json_command_label_equals_the_registered_name(env) -> None:
    db = env
    _add(db, "hole_y", "TOP.hole_1")
    rc, text = _list(db, "--json")
    assert rc == 0, text
    payload = _payload(text)
    assert payload["command"] == "ctq list", payload
    assert payload["ok"] is True, payload


def test_empty_scope_is_stated_not_silent(env) -> None:
    db = env
    rc, text = _list(db)
    assert rc == 0, text
    assert "0" in text, repr(text)
    assert P in text, f"要带作用域，否则读不出这个 0 是哪个项目/租户的 0：\n{text}"


def test_other_statuses_show_verbatim_under_all(env) -> None:
    db = env
    rid = _add(db, "hole_z", "TOP.hole_1")
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
    store.set_status(rid, "stale", tenant_id=T, project_id=P)

    rc, text = _list(db, "--json", "--all")
    assert rc == 0, text
    got = {r["record_id"]: r["status"] for r in _payload(text)["records"]}
    assert got.get(rid) == "stale", got

    rc2, dflt = _list(db, "--json")
    assert rc2 == 0, dflt
    p2 = _payload(dflt)
    assert p2["records"] == [], f"stale 既不是 active，也不该出现在默认视图：{p2}"
    assert p2.get("excluded", {}).get("stale") == 1, p2


def test_unreadable_store_is_not_reported_as_zero_records(tmp_path) -> None:
    """库文件根本不是 sqlite ⇒ 退 2，且**不许**产出任何「0 条」读数。

    钉的是 `_open_store` 那一层（`commands_truth.py:24`）。
    """
    bogus = tmp_path / "not-a-db.db"
    bogus.write_text("这不是 sqlite 库\n", encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["ctq", "list", "--db", str(bogus), "--project", P])
    text = buf.getvalue()
    assert rc == 2, text
    assert "0 条" not in text, f"坏路径不许给出「没有记录」的读数：\n{text}"


def test_mid_read_failure_is_not_a_zero_reading(monkeypatch, env) -> None:
    """库打得开、`list_ctq` 抛在手里 ⇒ 同样退 2，不许把异常吞成「0 条」。

    与上一条必须分开钉（第 62 片电池教的）：只拿"文件不是 sqlite 库"当输入时，
    异常其实在 `_open_store` 就被接住了，命令里那段 try/except **根本没到**——
    于是"把读失败读成空清单"那个变异在只测前者时活了下来（SURVIVED）。
    """
    db = env
    _add(db, "hole_v", "TOP.hole_1")
    import aipd_os.product_truth.ctq as ctq_mod

    def boom(*_a: Any, **_k: Any) -> dict:
        raise RuntimeError("模拟：读到一半底层断了")

    monkeypatch.setattr(ctq_mod, "list_ctq", boom)
    rc, text = _list(db)
    assert rc == 2, text
    assert "0 条" not in text, f"异常被吞成就成了「没有记录」：\n{text}"


def test_listing_writes_no_audit_row(env) -> None:
    """只读面不许污染审计通道：`audit_log` 回答的是「谁改了事实」。

    反向对照同批跑（写命令必须留行）：否则本用例只证明了审计通道本来就不通，
    而不是「读面刻意不写」。
    """
    db = env
    rid = _add(db, "hole_w", "TOP.hole_1")
    before = len(AIPDStateDB(str(db)).list_audit(limit=500))
    rc, text = _list(db, "--json")
    assert rc == 0, text
    assert len(AIPDStateDB(str(db)).list_audit(limit=500)) == before, \
        "查看一次就在审计里留了一行，「谁改了限值」再也问不出来"
    assert main(["ctq", "deprecate", "--db", str(db), "--project", P, "--record", rid,
                 "--reason", "本用例的反向对照", "--by", "潘工"]) == 0
    after = len(AIPDStateDB(str(db)).list_audit(limit=500))
    assert after > before, "反向对照不成立：写命令也没留审计行，上一条断言就是空的"


def test_readme_quickref_lists_the_new_command(env) -> None:
    """速查要有一行行首可执行写法——第 60 片那把尺子判的就是这个面。"""
    lines = [ln.strip() for ln in README.read_text(encoding="utf-8").splitlines()]
    assert any(ln.startswith("aipd ctq list") for ln in lines), \
        "README 的 ctq 分组里要有 `aipd ctq list …` 这一行（行首、可复制执行）"


def test_limits_print_verbatim_not_six_significant_digits(env) -> None:
    """合格域原样打。第 62 片复核前用的是 `f"{low:g}"`：实测 `format(8.050001,'g') == '8.05'`，
    一条 8.050001 的上限会被印成 8.05 —— 而这条面存在的理由就是回答"限值到底是几"。"""
    db = env
    _add(db, "hole_precise", "TOP.hole_5", lower="7.950001", upper="8.050001")
    rc, text = _list(db)
    assert rc == 0, text
    assert "7.950001" in text and "8.050001" in text, text
    assert "[7.95, 8.05]" not in text, f"读数被舍入成了另一个合格域：\n{text}"


def test_counts_are_self_consistent_across_the_two_views(env) -> None:
    """`total == returned + Σexcluded` 是这条读面自己的守恒；不守恒就等于在漏记录。"""
    db = env
    _add(db, "hole_k1", "TOP.hole_1")
    _add(db, "hole_k2", "TOP.hole_2")
    keep = _add(db, "hole_k3", "TOP.hole_3")
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
    store.set_status(keep, "stale", tenant_id=T, project_id=P)

    rc, dflt = _list(db, "--json")
    assert rc == 0, dflt
    p = _payload(dflt)
    assert p["total"] == p["returned"] + sum(p["excluded"].values()), p
    assert p["returned"] == 2 and p["excluded"] == {"stale": 1}, p
    assert len(p["records"]) == p["returned"], p

    rc2, allp = _list(db, "--json", "--all")
    assert rc2 == 0, allp
    q = _payload(allp)
    assert q["excluded"] == {} and q["returned"] == q["total"] == 3, q
    assert q["statuses"] == "all" and p["statuses"] == "active", (q["statuses"], p["statuses"])


def test_default_note_does_not_claim_superseded_is_the_only_retirement(env) -> None:
    """那句口径注不能把"退出分母"写成只有 superseded。

    实测（第 62 片复核）：`release_manifest._collect_ctq` 把**全部**非 active 态都请出分母，
    superseded 特殊的只有一点——对它只出非阻断点名；另外缺 `metadata.feature` 的
    active 记录门口判 `ctq_missing_feature` 阻断，而本视图照样列出。
    """
    db = env
    _add(db, "hole_note", "TOP.hole_1")
    rc, text = _list(db)
    assert rc == 0, text
    assert "唯一" not in text, f"口径注又把例外说满了：\n{text}"
    assert "非 active" in text and "ctq_missing_feature" in text, \
        f"口径注要同时点出两处与发布分母的差别：\n{text}"


def test_failure_paths_emit_no_success_payload(env, tmp_path, monkeypatch) -> None:
    """两条读失败面带 `--json` 时：退 2，且 stdout 上不许出现 `"ok": true` 的成功件。"""
    bogus = tmp_path / "junk.db"
    bogus.write_text("不是库\n", encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["ctq", "list", "--db", str(bogus), "--project", P, "--json"])
    text = buf.getvalue()
    assert rc == 2, text
    assert '"ok": true' not in text, text

    import aipd_os.product_truth.ctq as ctq_mod

    def boom(*_a: Any, **_k: Any) -> dict:
        raise RuntimeError("模拟：中途断")

    monkeypatch.setattr(ctq_mod, "list_ctq", boom)
    rc2, text2 = _list(env, "--json")
    assert rc2 == 2, text2
    assert '"ok": true' not in text2, text2
