"""链头那一格：`aipd ctq add`（F-CTQ-PRODUCER 第 56 片）。

实测前提（本轮复算过，不是叙述）：`record_type="ctq"` 在 `src/` 侧只有四个读者
—— `release_manifest.py:69`（发布证据分母）、`cad/spec_from_truth.py:55`（图纸声明输入）、
`cli/commands_drawing.py:86` 与 `cad/spec_rework.py:84`（出声明与返工重算）——
而全仓排除 `tests/` 后**没有任何写入点**；PI gate 只写 `requirement`/`feature`
（`product_intelligence/gate.py:455,476`），Feature 模型里连一个公差字段都没有
（`product_intelligence/models.py:507-519`）。于是 `aipd drawing spec` 在真库里
永远只能对着 0 条 CTQ 跑。

钉五组：
1. **写出来的记录必须喂得饱每一个读者**：三个读者要的字段一条不缺；
2. **信任级不自封**：没有 `--test-ref` 就是 `unverified`（P0-08 同一条推导函数）；
3. **门口就拒的四种不合法**：标称不在域内、上下限倒置、数值解析不出、
   认识论态不在 `_derive_trust` 那五个字母里；外加"同一图纸尺寸已有 active CTQ"
   ——因为 `spec_from_truth` 遇到两条抢一个尺寸会把**两条一起撤回**；
4. **空声明不再被读成完成**：库里没有 active CTQ 时 `drawing spec` 旧行为是
   写一份 `features: []` + 落一条无引用的血缘记录 + `ok:true` 退 0（本轮实测），
   现在判未收口：文件不写、血缘不落、`empty_declaration` 为真；
5. **端到端**：公开命令声明 CTQ → 出声明 → 改限值 → `truth drift` 发现 →
   `truth sweep` 落刀 → `truth rework` 把声明文件按新限值重写。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore
from aipd_os.release_manifest import _collect_ctq
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
T = "default"
P = "CTQ-ADD"
README = ROOT / "README.md"

BASE = ["--feature", "hole_Ø8", "--drawing-feature", "TOP.hole_1",
        "--nominal", "8.0", "--lower", "7.95", "--upper", "8.05",
        "--inspection", "CMM", "--by", "潘工"]


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant(T)
    state.init_project(T, P, "链头生产者测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _ctqs(db):
    return [r for r in _store(db).query(record_type="ctq", tenant_id=T, project_id=P)]


def _add(db, *extra, project=P):
    return main(["ctq", "add", "--db", str(db), "--project", project] + BASE
                + list(extra))


def _json_out(db, capsys, *extra, project=P):
    rc = _add(db, "--json", *extra, project=project)
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return rc, payload


def _spec(db, tmp_path, capsys, name="spec.json"):
    out = tmp_path / name
    rc = main(["drawing", "spec", "--db", str(db), "--project", P,
               "--out", str(out), "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return rc, payload, out


# ---------- 一、写出来的记录喂得饱读者 ----------

def test_declared_record_carries_every_field_a_reader_requires(env, capsys):
    tmp_path, db = env
    rc, payload = _json_out(db, capsys)
    assert rc == 0 and payload["created"] is True, payload
    rec = _ctqs(db)[0]
    meta = rec.metadata or {}
    # 读者一（发布证据 _collect_ctq）：feature + inspection_method + 上下限
    assert meta["feature"] == "hole_Ø8" and meta["inspection_method"] == "CMM"
    assert (meta["lower_limit"], meta["upper_limit"]) == (7.95, 8.05)
    # 读者二（spec_from_truth）：drawing_feature + nominal，缺一个就是一条 gap
    assert meta["drawing_feature"] == "TOP.hole_1" and meta["nominal"] == 8.0
    # 出处：谁声明的必须在记录里，不留机器缺省（第 32/34/35 片那一族）
    assert meta["declared_by"] == "潘工" and "潘工" in (rec.source.note or "")
    assert rec.status == "active" and rec.record_id == payload["record_id"]


def test_the_reader_itself_accepts_the_declared_record(env, capsys):
    """不靠自己抄字段名判对错：直接把记录交给读者 `_collect_ctq` 看它有没有意见。"""
    _, db = env
    assert _add(db) == 0
    issues: list[dict] = []
    by_id = _collect_ctq(_store(db), issues)
    assert len(by_id) == 1, by_id
    kinds = {i["kind"] for i in issues}
    assert not (kinds & {"ctq_missing_feature", "ctq_missing_inspection", "no_ctq"}), issues
    assert by_id[next(iter(by_id))]["feature"] == "hole_Ø8"


# ---------- 二、信任级不自封 ----------

def test_declaration_without_test_ref_is_not_self_styled_verified(env, capsys):
    _, db = env
    rc, payload = _json_out(db, capsys)
    assert rc == 0
    assert payload["trust_level"] == "unverified", (
        "属主说一句话就 verified，等于把'有人提了要求'读成'要求已被验证'（P0-08）")


def test_test_ref_and_verifiable_status_raise_trust(env, capsys):
    _, db = env
    rc, payload = _json_out(db, capsys, "--epistemic", "V",
                            "--test-ref", "lab/CMM-017.json")
    assert rc == 0 and payload["trust_level"] == "verified", payload
    assert _ctqs(db)[0].metadata["test_refs"] == ["lab/CMM-017.json"]


def test_verifiable_status_without_ref_stays_downgraded(env, capsys):
    """两档的中间面：V 但没有引用 ⇒ medium（既不是自封 verified，也不是一笔抹平）。"""
    _, db = env
    rc, payload = _json_out(db, capsys, "--epistemic", "V")
    assert rc == 0 and payload["trust_level"] == "medium", payload


# ---------- 三、门口就拒 ----------

def test_nominal_outside_the_domain_is_refused_and_nothing_is_written(env, capsys):
    _, db = env
    rc = main(["ctq", "add", "--db", str(db), "--project", P,
               "--feature", "slot", "--drawing-feature", "TOP.slot",
               "--nominal", "9.9", "--lower", "1.0", "--upper", "2.0",
               "--inspection", "CMM", "--by", "潘工"])
    out = capsys.readouterr().out
    assert rc == 2 and "标称" in out, out
    assert _ctqs(db) == [], "被拒的声明不许留下半条记录"


def test_inverted_limits_are_refused(env):
    _, db = env
    rc = main(["ctq", "add", "--db", str(db), "--project", P,
               "--feature", "slot", "--drawing-feature", "TOP.slot",
               "--nominal", "1.5", "--lower", "2.0", "--upper", "1.0",
               "--inspection", "CMM", "--by", "潘工"])
    assert rc == 2
    assert _ctqs(db) == []


def test_unparsable_number_names_the_field(env, capsys):
    """数值校验留在 declare_ctq 一处（argparse 不转 float），所以错误文案必须是 ours。"""
    _, db = env
    rc = main(["ctq", "add", "--db", str(db), "--project", P,
               "--feature", "slot", "--drawing-feature", "TOP.slot",
               "--nominal", "八", "--lower", "1.0", "--upper", "2.0",
               "--inspection", "CMM", "--by", "潘工"])
    out = capsys.readouterr().out
    assert rc == 2, f"解析不出的数值必须被拒，不能当'没给'往下走（rc={rc}）"
    assert "--nominal" in out, f"文案要点名是哪一格，拿到：{out!r}"
    assert _ctqs(db) == []


def test_second_ctq_on_the_same_drawing_size_is_refused_by_name(env):
    """`spec_from_truth` 对同一尺寸两条公差会把两条一起撤回 ⇒ 这里先在门口拦。"""
    _, db = env
    assert _add(db) == 0
    rc = main(["ctq", "add", "--db", str(db), "--project", P,
               "--feature", "hole_Ø8.1", "--drawing-feature", "TOP.hole_1",
               "--nominal", "8.1", "--lower", "8.0", "--upper", "8.2",
               "--inspection", "CMM", "--by", "潘工"])
    assert rc == 2
    assert len(_ctqs(db)) == 1, "抢同一尺寸的第二条不许进库"


def test_idempotent_re_declaration_reuses_the_record(env, capsys):
    _, db = env
    _, first = _json_out(db, capsys)
    rc, again = _json_out(db, capsys)
    assert rc == 0 and again["created"] is False
    assert again["record_id"] == first["record_id"]
    assert len(_ctqs(db)) == 1, "重跑同一条声明不许攒出重复要求"


def test_unknown_epistemic_letter_is_refused(env):
    _, db = env
    rc = _add(db, "--epistemic", "S")
    assert rc == 2, "字母表不许自己扩：那套字母是 _derive_trust 的分支面"


def test_author_is_required_not_defaulted(env, capsys):
    """`--by` 没有机器缺省值（AI 不自批、不拿 system 冒充属主）。"""
    _, db = env
    with pytest.raises(SystemExit) as boom:
        main(["ctq", "add", "--db", str(db), "--project", P,
              "--feature", "hole", "--drawing-feature", "TOP.hole",
              "--nominal", "8.0", "--lower", "7.95", "--upper", "8.05",
              "--inspection", "CMM"])
    assert boom.value.code == 2
    # argparse 的 usage 走 stderr；SystemExit 的值只有码，文案不在那儿
    err = capsys.readouterr().err
    assert "--by" in err, f"缺必填旗子时要点名是哪一面，拿到：{err!r}"
    assert _ctqs(db) == []


# ---------- 四、空声明不算完成 ----------

def test_empty_library_yields_no_spec_file_and_no_lineage(env, capsys, tmp_path):
    """本轮实测到的旧洞：0 条 CTQ 时写 features=[] + 落一条无引用血缘 + 退 0。"""
    _, db = env
    rc, payload, out = _spec(db, tmp_path, capsys)
    assert rc == 4, "空声明不是交付物，退 0 等于把'还没人声明要求'读成'声明已完成'"
    assert payload["empty_declaration"] is True
    assert payload["ok"] is False and payload["out"] is None
    assert not out.exists(), "未收口不许把空 spec 落到盘上"
    rows = [r for r in _store(db).query(record_type="artifact_version",
                                        tenant_id=T, project_id=P)]
    assert rows == [], f"空声明不该占一条血缘版本记录：{rows}"


def test_one_declared_ctq_is_enough_to_emit_a_spec(env, capsys, tmp_path):
    _, db = env
    assert _add(db) == 0
    rc, payload, out = _spec(db, tmp_path, capsys)
    assert rc == 0 and payload["empty_declaration"] is False, payload
    assert payload["lineage"]["edges"] == 1
    assert json.loads(out.read_text(encoding="utf-8"))["features"][0]["feature"] \
        == "TOP.hole_1"


def test_scope_does_not_leak(env, capsys, tmp_path):
    """另一个项目的 CTQ 不许出现在本项目的声明里。"""
    _, db = env
    other = "CTQ-OTHER"
    AIPDStateDB(str(db)).init_project(T, other, "对照作用域", "evidence")
    assert _add(db, project=other) == 0
    rc, payload, _ = _spec(db, tmp_path, capsys)
    assert rc == 4 and payload["ctq_records"] == 0, (
        f"跨作用域漏了：{payload}")


# ---------- 五、端到端：链头到返工 ----------

def _change_upper_limit(db, value=8.10):
    """属主改了要求：今天没有 revise 命令，改限值只能走库层（那一格留给下一片）。"""
    store = _store(db)
    ctq = _ctqs(db)[0]
    meta = dict(ctq.metadata)
    meta["upper_limit"] = value
    store.update(ctq.record_id, tenant_id=T, project_id=P, metadata=meta)
    return ctq, store


def _drifted(db):
    from aipd_os.cli.commands_drift import build_resolvers
    from aipd_os.product_truth.drift import DRIFTED, scan_drift

    report = scan_drift(_store(db), resolvers=build_resolvers(str(db), P, T),
                        tenant_id=T, project_id=P)
    return {str(r["record_id"]) for r in report["buckets"][DRIFTED]}, report


def test_ctq_change_is_invisible_to_drift_and_sweep(env, capsys, tmp_path):
    """钉住本片实测到的边界：`drawing_spec` 记录的身份键是**声明文件的哈希**，
    所以"改了 CTQ 但没人 propagate"这条路 drift/sweep 都看不见。
    不是猜测——本轮先按"应该能发现"写断言，它红了，才改成钉缺席（F-DRIFT-5 的靶子）。
    """
    _, db = env
    assert _add(db) == 0
    rc, payload, _ = _spec(db, tmp_path, capsys)
    assert rc == 0
    spec_record = payload["lineage"]["record_id"]
    _change_upper_limit(db)

    drifted, report = _drifted(db)
    assert drifted == set(), (
        f"这一格今天应该看不见（signature 是文件哈希）：{report}")
    # sweep 的前半就是 drift ⇒ 它也落不到这一刀；库里没有任何东西被标 stale
    assert main(["truth", "sweep", "--db", str(db), "--project", P]) == 0
    assert spec_record not in _drifted(db)[0]
    statuses = {str(r.record_id): str(r.status)
                for r in _store(db).query(record_type="artifact_version",
                                          tenant_id=T, project_id=P)}
    assert statuses[spec_record] == "active", (
        "sweep 不该在看不见漂移时顺手把记录标 stale：那等于伪造触发依据")


def test_declared_ctq_feeds_spec_propagate_and_rework(env, capsys, tmp_path):
    """公开命令走通的一整条链（这是本片存在的理由）：
    声明 CTQ → 出声明 → 改限值 → propagate 标 stale 并建任务 → rework 按新限值重写文件。"""
    _, db = env
    assert _add(db) == 0
    rc, payload, out = _spec(db, tmp_path, capsys)
    assert rc == 0
    assert "7.95" in out.read_text(encoding="utf-8")
    spec_record = payload["lineage"]["record_id"]

    ctq, store = _change_upper_limit(db)
    assert main(["truth", "propagate", "--db", str(db), "--project", P,
                 "--upstream", str(ctq.record_id)]) == 4
    statuses = {str(r.record_id): str(r.status)
                for r in store.query(record_type="artifact_version",
                                     tenant_id=T, project_id=P)}
    assert statuses[spec_record] == "stale", (
        f"propagate 没把那份声明标 stale：{statuses}")

    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--all-pending"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "8.1" in text, f"返工没按新限值重写声明：{text[:200]}"
    edges = {(e["upstream_id"], e["downstream_id"])
             for e in LineageGraph(store, tenant_id=T, project_id=P).edges(
                 tenant_id=T, project_id=P)}
    assert (str(ctq.record_id), spec_record) in edges, edges


# ---------- 六、命令面镜像（漏一处就该红，而不是靠人记） ----------

def test_command_surface_mirrors_are_all_present(env):
    """新公开命令的四处镜像：契约 / COMMAND_FUNCS / argparse / README。"""
    from aipd_os.cli.command_contract import get_command_entry
    from aipd_os.cli.commands import COMMAND_FUNCS

    entry = get_command_entry("ctq add")
    assert entry is not None, "ctq add 没登记进 command_contract"
    assert entry.status.value == "public", entry.status
    assert {"--db", "--project", "--by", "--inspection"} <= set(entry.requires_args)
    assert COMMAND_FUNCS["ctq add"].__name__ == "cmd_truth_ctq_add"
    # argparse 面：旗子必须真挂在 `ctq add` 那个子解析器上（AST 反查 dest，不靠人肉比对文案）
    tree = ast.parse((ROOT / "src/aipd_os/cli/main.py").read_text(encoding="utf-8"))
    declared = {str(getattr(node.args[0], "value", ""))
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "ca" and node.args}
    assert declared, "AST 没读到任何旗子 ⇒ 这把门禁本身是恒真的，不能算绿"
    assert {"--db", "--project", "--feature", "--drawing-feature", "--nominal",
            "--lower", "--upper", "--inspection", "--by"} <= declared, declared
    assert "aipd ctq add" in README.read_text(encoding="utf-8"), (
        "README 的命令速查没这一条 ⇒ 用户看不到链头已经有生产者")


def test_handler_is_reachable_only_through_the_cli(env, capsys):
    """premise：`_number` 的字符串路径必须由 CLI 覆盖（否则 argv 与 API 两套语义）。"""
    _, db = env
    from aipd_os.product_truth.ctq import CtqDeclarationError, _number

    assert _number("7.95", "--lower") == 7.95      # argv 来的就是字符串
    for bad in ("", "nan", "inf", "八", None, True):
        with pytest.raises(CtqDeclarationError):
            _number(bad, "--nominal")
    assert _add(db) == 0                            # CLI 全字符串路径通
