"""链头的改动入口：`aipd ctq revise` / `aipd ctq deprecate`（F-CTQ-REVISION 第 59 片）。

第 56 片只给了 `add`，所以在本片之前"改一条已声明 CTQ 的限值"只能走库层 `store.update`
——登记表里第 56 片那条限制（「谁在什么时候把 8.05 改成 8.10 缺一个审计入口」）就是这么留着的，
本片把它换成新的限制句（见 `src/aipd_os/registry_data.py` 的 `product_truth.ctq_declaration`）。
本片补 revise / deprecate，判据形状借本轮实读的 dbt model versions
（"新版本落地、latest 才是 canonical、旧版留在名单里"）与 django-simple-history
（"历史行带 user 与 change reason，不改写原文"），落在本仓既有的
`superseded` 状态与 `AIPDStateDB.add_audit(before/after)` 通道上，不引依赖。

钉五组：
1. 修订的形状：另起一条、旧的标 superseded 并留 `superseded_by` 链、版本号跟着走；
2. 审计：改了必留一行（actor = `--by`，含前后限值）；同值修订不另起版本也不写审计；
   审计写不进去判未收口（退码 4，且 `--json` 的 ok 同向）；
3. 门口就拒的几种：记录不存在 / 不是 ctq / 已不在有效名单 / 限值不合法 /
   `--reason` 空 / `--replaced-by` 指向不存在的记录 —— 且**一条都不写**；
4. 链条：revise → drift 点名 → sweep 落刀 → rework 按新值重写 → drift 转绿；
   deprecate 探的是另一半：撤回最后一条要求时，返工不该把声明自证成空；
5. 命令面镜像：契约 / COMMAND_FUNCS / argparse 旗子 / README 四处，缺一条就红。
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import ProductTruthStore
from aipd_os.product_truth.models import TruthRecord
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
T = "default"
P = "CTQ-REVISE"

BASE = ["--feature", "hole_Ø8", "--drawing-feature", "TOP.hole_1",
        "--nominal", "8.0", "--lower", "7.95", "--upper", "8.05",
        "--inspection", "CMM", "--by", "潘工"]


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant(T)
    state.init_project(T, P, "链头改动入口", "evidence")
    return SimpleNamespace(tmp=tmp_path, db=db, state=state)


def _store(env):
    return ProductTruthStore(str(env.db), tenant_id=T, project_id=P)


def _ctqs(env):
    return _store(env).query(record_type="ctq", tenant_id=T, project_id=P)


def _audits(env):
    return list(reversed(env.state.list_audit(limit=50)))


def _add(env):
    return main(["ctq", "add", "--db", str(env.db), "--project", P] + BASE)


def _revise(env, record, *flags, by="潘工"):
    return main(["ctq", "revise", "--db", str(env.db), "--project", P,
                 "--record", str(record)] + list(flags) + ["--by", by])


def _deprecate(env, record, *flags, reason="客户取消该要求", by="潘工"):
    # `reason` 设成关键字参数：写成位置参数的话，调用处一传 "--replaced-by"
    # 就会把它吃掉，argparse 于是报「--reason: expected one argument」——
    # 看着像被测代码的问题，其实是测试自己的形状错。
    return main(["ctq", "deprecate", "--db", str(env.db), "--project", P,
                 "--record", str(record), "--reason", reason,
                 "--by", by] + list(flags))


def _declare(env):
    """种一条声明（链头 + 图纸声明记录），返回 (声明文件, 声明记录号)。"""
    assert _add(env) == 0
    out = env.tmp / "spec.json"
    assert main(["drawing", "spec", "--db", str(env.db), "--project", P,
                 "--out", str(out)]) == 0
    rec = _store(env).query(record_type="artifact_version",
                            tenant_id=T, project_id=P)[0]
    return out, rec


def _quiet(fn):
    """跑一次命令，收 stdout/stderr 但不让它们刷屏（argparse 的拒辞在 stderr，
    且它是以 SystemExit 的形式离开 `main` 的，所以要在这里折成返回码）。"""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = fn()
    except SystemExit as exc:                      # argparse 的 required/usage 拒绝
        rc = int(exc.code) if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


# ---------- 一、修订的形状 ----------

def test_revise_supersedes_the_old_record_and_chains_to_the_new(env):
    assert _add(env) == 0
    old = _ctqs(env)[0]
    assert _revise(env, old.record_id, "--upper", "8.10", "--note", "放宽装配间隙") == 0

    rows = {str(r.record_id): r for r in _ctqs(env)}
    assert len(rows) == 2, rows
    assert str(rows[old.record_id].status) == "superseded"
    active = [r for r in rows.values() if str(r.status) == "active"]
    assert len(active) == 1
    new = active[0]
    meta_old, meta_new = rows[old.record_id].metadata, new.metadata
    assert meta_old["superseded_by"] == str(new.record_id)
    assert meta_old["superseded_reason"] == "放宽装配间隙"
    assert meta_old["superseded_by_actor"] == "潘工"
    assert meta_new["upper_limit"] == 8.10
    assert meta_new["lower_limit"] == 7.95, "没给的旗子必须沿用旧值，不是清空"
    assert int(new.version) == int(rows[old.record_id].version) + 1, (
        "链上每条都叫 v1 的话，「改了几次」又得回去数审计行")


def test_revise_to_the_same_values_creates_nothing(env, capsys):
    """同值修订不动库：不另起版本、不写审计行（否则审计次数会虚高于真实改动）。

    这条是本轮 smoke 实测出来的：`supersedes` 会把被修订的那条从查重名单里摘掉
    （不摘就永远修订不动自己），于是"改回同一个值"在 declare 眼里成了一条新声明。
    """
    assert _add(env) == 0
    rid = _ctqs(env)[0].record_id
    before = {str(r.record_id) for r in _ctqs(env)}
    assert _revise(env, rid, "--upper", "8.05", "--nominal", "8.000") == 0
    assert {str(r.record_id) for r in _ctqs(env)} == before
    assert _audits(env) == []
    assert "不另起版本" in capsys.readouterr().out


@pytest.mark.parametrize("flags, needle", [
    (["--upper", "7.90"], "必须严格小于上限"),
    (["--nominal", "9.5"], "不在"),
    (["--upper", "八"], "解析不出"),
])
def test_revise_refuses_invalid_domains_before_writing_anything(env, flags, needle,
                                                               capsys):
    """非法值退 2 且**一条都不写**：域内校验仍只有一处（declare_ctq），不复制一份。"""
    assert _add(env) == 0
    snapshot = {str(r.record_id): str(r.status) for r in _ctqs(env)}
    assert _revise(env, _ctqs(env)[0].record_id, *flags) == 2
    assert {str(r.record_id): str(r.status) for r in _ctqs(env)} == snapshot
    assert needle in capsys.readouterr().out
    assert _audits(env) == []


def test_revise_refuses_missing_inactive_and_foreign_records(env, capsys):
    assert _add(env) == 0
    rid = _ctqs(env)[0].record_id
    assert _revise(env, "NO-404", "--upper", "8.10") == 2
    assert "不存在" in capsys.readouterr().out

    assert _deprecate(env, rid) == 0
    capsys.readouterr()
    assert _revise(env, rid, "--upper", "8.10") == 2
    assert "不是 active" in capsys.readouterr().out, "停用后再修订会静默分裂出两条有效要求"

    foreign = _store(env).add(TruthRecord(record_type="requirement", content="别的要求"),
                             tenant_id=T, project_id=P)
    assert _revise(env, foreign, "--upper", "8.10") == 2
    assert "不是 ctq" in capsys.readouterr().out


# ---------- 二、审计入口 ----------

def test_revise_writes_one_audit_row_with_both_values(env):
    assert _add(env) == 0
    rid = _ctqs(env)[0].record_id
    assert _revise(env, rid, "--upper", "8.10") == 0
    rows = [r for r in _audits(env) if r["action"] == "ctq.revise"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["actor"] == "潘工" and row["tenant_id"] == T and row["project_id"] == P
    before, after = json.loads(row["before_json"]), json.loads(row["after_json"])
    assert (before["upper_limit"], after["upper_limit"]) == (8.05, 8.10), (before, after)
    assert before["record_id"] == str(rid) and after["record_id"] != str(rid)
    assert "8.05" in row["before_json"] and "8.1" in row["after_json"]


def test_author_is_required_on_both_new_commands(env):
    """`--by` 不留机器缺省值：改了要求却不知道是谁改的，审计行就成了假账。"""
    assert _add(env) == 0
    rid = _ctqs(env)[0].record_id
    for argv in (["ctq", "revise", "--db", str(env.db), "--project", P,
                  "--record", str(rid), "--upper", "8.10"],
                 ["ctq", "deprecate", "--db", str(env.db), "--project", P,
                  "--record", str(rid), "--reason", "客户取消"]):
        rc, _out, err = _quiet(lambda a=argv: main(a))
        assert rc == 2, argv
        assert "the following arguments are required: --by" in err, (argv, err)


def test_unwritable_audit_is_not_a_clean_success(env, monkeypatch, capsys):
    """审计写不进去 ⇒ 退码 4 且 `--json` 的 ok 同向：数据改了但没人知道是谁改的。"""
    assert _add(env) == 0
    rid = _ctqs(env)[0].record_id
    from aipd_os.state import db as dbmod

    def boom(self, *a, **k):
        raise RuntimeError("审计表被锁")

    monkeypatch.setattr(dbmod.AIPDStateDB, "add_audit", boom)
    rc, out, _err = _quiet(lambda: main(
        ["ctq", "revise", "--db", str(env.db), "--project", P, "--record", str(rid),
         "--upper", "8.10", "--by", "潘工", "--json"]))
    assert rc == 4, out
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["ok"] is False and "审计表被锁" in payload["audit_error"], payload
    assert payload["changed"] is True, "数据确实已改，不许把半收口报成什么都没发生"


# ---------- 三、停用 ----------

def test_deprecate_requires_reason_and_a_real_successor(env, capsys):
    assert _add(env) == 0
    rid = _ctqs(env)[0].record_id
    assert _deprecate(env, rid, reason="   ") == 2
    assert "不能为空" in capsys.readouterr().out

    assert _deprecate(env, rid, "--replaced-by", "NO-9") == 2
    assert "不存在" in capsys.readouterr().out
    assert str(_ctqs(env)[0].status) == "active", "被拒的停用一个字都不该写"

    other = _store(env).add(TruthRecord(record_type="requirement", content="另一条"),
                           tenant_id=T, project_id=P)
    assert _deprecate(env, rid, "--replaced-by", str(other), reason="客户取消") == 0
    meta = _ctqs(env)[0].metadata
    assert meta["superseded_by"] == str(other) and meta["superseded_reason"] == "客户取消"


def test_deprecate_is_audited_once_and_not_repeatable(env, capsys):
    assert _add(env) == 0
    rid = _ctqs(env)[0].record_id
    assert _deprecate(env, rid) == 0
    rows = [r for r in _audits(env) if r["action"] == "ctq.deprecate"]
    assert len(rows) == 1
    assert json.loads(rows[0]["before_json"])["status"] == "active"
    assert json.loads(rows[0]["after_json"])["status"] == "superseded"
    assert _deprecate(env, rid) == 2, "重复停用会把时间刷成今天，掩盖第一次的改动时刻"
    assert len([r for r in _audits(env) if r["action"] == "ctq.deprecate"]) == 1


# ---------- 四、链条 ----------

def test_revise_is_visible_to_drift_sweep_and_rework(env):
    """本片的理由：改限值之后不需要人记得 propagate，链条自己走到"声明按新值重写"。"""
    out, spec_rec = _declare(env)
    assert _revise(env, _ctqs(env)[0].record_id, "--upper", "8.10") == 0
    assert main(["truth", "drift", "--db", str(env.db), "--project", P]) == 4
    assert main(["truth", "sweep", "--db", str(env.db), "--project", P]) == 4
    assert str(_store(env).get(spec_rec.record_id).status) == "stale"
    assert main(["truth", "rework", "--db", str(env.db), "--project", P,
                 "--all-pending"]) == 0
    assert "8.1" in out.read_text(encoding="utf-8"), "返工没按新限值重写声明"
    assert main(["truth", "drift", "--db", str(env.db), "--project", P]) == 0
    # 新那条 CTQ 必须真的接进了声明的上游名单，否则下一次改动又会看不见
    refs = [str(r) for r in _store(env).get(spec_rec.record_id).metadata["ctq_refs"]]
    active = [str(r.record_id) for r in _store(env).query(
        record_type="ctq", status="active", tenant_id=T, project_id=P)]
    assert refs == active, (refs, active)


def test_deprecating_the_last_ctq_does_not_empty_the_declaration(env):
    """撤回最后一条要求时，返工**不该**把声明重写成一份空声明。

    第 56 片在**生产者**那一侧拒了"`features: []` 也算交付物"，这里探的是返工执行器
    有没有同一半守卫：要求被撤回是"分母少一条"，不是"这份产物完成了"。
    """
    out, _spec_rec = _declare(env)
    assert _deprecate(env, _ctqs(env)[0].record_id) == 0
    assert main(["truth", "drift", "--db", str(env.db), "--project", P]) == 4
    assert main(["truth", "sweep", "--db", str(env.db), "--project", P]) == 4
    rc = main(["truth", "rework", "--db", str(env.db), "--project", P,
               "--all-pending"])
    features = json.loads(out.read_text(encoding="utf-8")).get("features")
    assert features, f"返工把声明重写成了空声明（rc={rc}）：要求撤回不该由产物自证为空"
    assert rc == 4, "无要求可声明时返工不该报成功"


# ---------- 五、命令面镜像 ----------

def test_command_surface_mirrors_are_all_present(env):
    """两处新命令的四处镜像：契约 / COMMAND_FUNCS / argparse / README。"""
    import ast

    from aipd_os.cli.command_contract import get_command_entry
    from aipd_os.cli.commands import COMMAND_FUNCS

    tree = ast.parse((ROOT / "src/aipd_os/cli/main.py").read_text(encoding="utf-8"))
    for name, var, handler, flags in (
            ("ctq revise", "cr", "cmd_truth_ctq_revise",
             {"--db", "--project", "--record", "--by"}),
            ("ctq deprecate", "cd", "cmd_truth_ctq_deprecate",
             {"--db", "--project", "--record", "--reason", "--by"})):
        entry = get_command_entry(name)
        assert entry is not None, f"{name} 没登记进 command_contract"
        assert flags <= set(entry.requires_args), (name, entry.requires_args)
        assert COMMAND_FUNCS[name].__name__ == handler, name
        declared = {str(getattr(node.args[0], "value", ""))
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_argument"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == var and node.args}
        assert declared and flags <= declared, (name, sorted(declared))
        assert f"aipd {name}" in README.read_text(encoding="utf-8"), (
            f"README 的命令速查没有 {name} ⇒ 用户看不到改动入口")
