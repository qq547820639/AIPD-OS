"""`aipd truth history`（F-AUDIT-READER 第 63 片）：把 `audit_log` 变成问得出来的东西。

前提是一笔被记在两处的账：审计行本来就在写（`AIPDStateDB.add_audit` 有多个写入点），
但 `list_audit` **不分作用域**且默认 100 条**静默截断**——
`product_truth/ctq.py` 里原话是"读者一翻页就丢"，registry 那行的限制句是
「谁在什么时候把 8.05 改成 8.10」问得出、但要自己按 before/after JSON 筛。

形状借两处成熟实现（都逐字读过原件，理由与拒绝项写在 CHANGELOG v5.24 那格）：
`django/contrib/admin/models.py` 的 `LogEntry` 把结构化 JSON 在**读侧**渲染成人话、
默认 `-action_time` 最新在前；`collectiveidea/audited` 的 `audited_changes` 存 [旧,新] 值对、
`associated_with` 把归属键写在**写入侧**。本仓已有 tenant/project 两列与 before/after 两份
快照，所以借的是"读侧渲染 + 写入侧归属"这两条语义，不引依赖。

钉十二组，每组对着一个具体的说谎方式：
1. 命令真注册在 argparse 声明树上；
2. 作用域隔离：别的项目/租户的行不进来，`total` 也不许把它们算进来；
3. `--record` 要能命中**改之前**那个号（一次 revise 写两个号），且行头两个号都报；
4. 被 `--limit` 切掉必须显式说出来（`total`/`returned`/`truncated` 三件分开）；
4b. `--actor` 是作用域谓词：进 SQL 也进 total，不是"取回后再看一眼"；
4c. `--since` 带 `Z` 要归一成 `+00:00`——同一瞬间的两种写法，按字符串比会差一个边界行；
5. payload 不是合法 JSON 的行：算进 total、被 `unparseable_rows` 点名、
   渲染时说"比不了值"——**不许**折算成"那次没改东西"，也不许让查询抛；
6. `--since` 的时区归一（带 Z 与不带时区两种写法都收到同一个下界），未来时间 ⇒ 0 条；
7. 值要渲染出来（`upper_limit: 8.05 → 8.1`），只报"改了哪些字段"等于没闭缺口；
8. 只读不写：一行审计都不落，同批用写命令做反向对照；
9. 库不存在 ⇒ 退 2 且不产出「0 条」读数；带 `--json` 时不许出现 `"ok": true` 成功件；
10. README 速查行镜像（第 60 片那把尺子判的面）；
11. `--action` 精确匹配不做前缀通配（动作名里本来就有 `.`，通配会把过滤条件变成另一个查询）。
"""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import ProductTruthStore
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
T, P, Q = "default", "HIST-A", "HIST-B"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant(T)
    state.init_project(T, P, "改动史读面", "evidence")
    state.init_project(T, Q, "另一个项目", "evidence")
    return db


def _run(db, *extra: str) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["truth", "history", "--db", str(db), *extra])
    return rc, buf.getvalue()


def _payload(text: str) -> dict[str, Any]:
    return json.loads(text.strip().splitlines()[-1])


def _add(db, project: str, feature: str, drawing: str, upper: str = "8.05") -> str:
    with contextlib.redirect_stdout(io.StringIO()):
        rc = main(["ctq", "add", "--db", str(db), "--project", project,
                   "--feature", feature, "--drawing-feature", drawing,
                   "--nominal", "8.0", "--lower", "7.95", "--upper", upper,
                   "--inspection", "CMM", "--by", "潘工"])
    assert rc == 0
    store = ProductTruthStore(str(db), tenant_id=T, project_id=project)
    return str(next(r.record_id for r in store.query(record_type="ctq", tenant_id=T,
                                                     project_id=project)
                    if (r.metadata or {}).get("feature") == feature))


def _revise(db, project: str, record: str, upper: str) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return main(["ctq", "revise", "--db", str(db), "--project", project,
                     "--record", record, "--upper", upper, "--by", "张工",
                     "--note", "公差收紧"])


def _deprecate(db, project: str, record: str) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return main(["ctq", "deprecate", "--db", str(db), "--project", project,
                     "--record", record, "--reason", "合并到别的尺寸", "--by", "张工"])


def _latest(db, project: str) -> str:
    store = ProductTruthStore(str(db), tenant_id=T, project_id=project)
    rows = list(store.query(record_type="ctq", tenant_id=T, project_id=project))
    return str(sorted(rows, key=lambda r: int(r.version))[-1].record_id)


def _one_change(db, project: str, feature: str, drawing: str) -> str:
    """造**一条审计行**：add 之后 revise 一次。

    `ctq add` 今天不写审计行——创建的事实由记录自身的 `declared_by` 与 `created_at` 交代。
    所以"谁第一次声明了这条"在这张读面上看不见，那是写入侧的一格（另立一片，不混进本片）。
    """
    rid = _add(db, project, feature, drawing)
    assert _revise(db, project, rid, "8.10") == 0
    return rid


def _authority_paths() -> set[str]:
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


def test_truth_history_is_registered_on_the_argparse_tree(env) -> None:
    assert "truth history" in _authority_paths(), sorted(
        n for n in _authority_paths() if n.startswith("truth"))
    rc, text = _run(env, "--project", P)
    assert rc == 0, text


def test_scoped_to_tenant_and_project_in_both_views(env) -> None:
    """别的项目一行都不许进来；`total` 也不许把别人的行算成本作用的条数。"""
    db = env
    _one_change(db, P, "hole_a", "TOP.a1")
    _one_change(db, Q, "hole_b", "TOP.b1")
    rc, text = _run(db, "--project", P, "--json")
    assert rc == 0, text
    payload = _payload(text)
    assert payload["total"] == 1, payload
    assert {e["project_id"] for e in payload["entries"]} == {P}, payload["entries"]
    assert payload["scope"] == {"tenant_id": T, "project_id": P}, payload["scope"]

    rc2, other = _run(db, "--project", Q, "--json")
    assert rc2 == 0
    assert _payload(other)["total"] == 1, other
    # 租户不存在 ⇒ 0 条而不是把别人的租户捞进来
    rc3, none = _run(db, "--project", P, "--tenant", "no-such", "--json")
    assert rc3 == 0 and _payload(none)["total"] == 0, none


def test_record_filter_hits_the_before_side_and_names_both_ids(env) -> None:
    """一次 revise 写两个号（改的是 T-001、新行是 T-002）：按旧号查必须查到，
    且行头把两个号都报出来——只报新号会让人按旧号再也找不着。"""
    db = env
    old = _add(db, P, "hole_a", "TOP.a1")
    assert _revise(db, P, old, "8.10") == 0
    rc, text = _run(db, "--project", P, "--record", old)
    assert rc == 0, text
    assert "ctq.revise" in text, text
    assert f"{old} →" in text, f"行头没把前后两个记录号都报出来：\n{text}"
    rcj, asjson = _run(db, "--project", P, "--record", old, "--json")
    assert rcj == 0, asjson
    hit = _payload(asjson)
    assert hit["total"] == 1 and hit["returned"] == 1, hit
    assert hit["filters"]["record_id"] == old, hit
    rc2, none = _run(db, "--project", P, "--record", "R-不存在的号")
    assert rc2 == 0, none
    assert "ctq.revise" not in none, none
    assert "0 条" in none, none
    rc3, notmine = _run(db, "--project", P, "--record", "R-不存在的号", "--json")
    assert _payload(notmine)["total"] == 0, _payload(notmine)


def test_limit_truncation_is_stated_not_hidden(env) -> None:
    """`--limit` 切掉的那些必须说出来：三件（total / returned / truncated）分开数。"""
    db = env
    _one_change(db, P, "hole_a", "TOP.a1")
    assert _deprecate(db, P, _latest(db, P)) == 0
    rc, text = _run(db, "--project", P, "--limit", "1", "--json")
    assert rc == 0, text
    payload = _payload(text)
    assert payload["total"] == 2 and payload["returned"] == 1, payload
    assert payload["truncated"] is True, payload
    assert len(payload["entries"]) == 1, payload

    rc2, prose = _run(db, "--project", P, "--limit", "1")
    assert rc2 == 0, prose
    assert "还有 1 条没给出" in prose and "--limit 1" in prose, prose


def test_actor_filter_scopes_without_touching_other_peoples_rows(env) -> None:
    """`--actor` 是作用域谓词：进 SQL、也进 total，不是"取回后再看一眼"。"""
    db = env
    _one_change(db, P, "hole_a", "TOP.a1")
    assert _deprecate(db, P, _latest(db, P)) == 0
    rc, both = _run(db, "--project", P, "--actor", "张工", "--json")
    assert rc == 0, both
    assert _payload(both)["total"] == 2, _payload(both)
    rc2, nobody = _run(db, "--project", P, "--actor", "没有这个人", "--json")
    assert rc2 == 0, nobody
    payload = _payload(nobody)
    assert payload["total"] == 0 and payload["returned"] == 0, payload


def test_unparseable_payload_is_counted_not_folded(env) -> None:
    """一行脏 payload：算进 total、被 unparseable_rows 点名、渲染时说"比不了值"。

    压成"那次没改东西"或让整条查询抛 malformed JSON，都是把数据缺陷读成读数。
    """
    db = env
    _one_change(db, P, "hole_a", "TOP.a1")
    with sqlite3.connect(str(db)) as con:
        con.execute("INSERT INTO audit_log(actor,action,project_id,tenant_id,timestamp,"
                    "before_json,after_json) VALUES(?,?,?,?,?,?,?)",
                    ("机器", "legacy.import", P, T, "2020-01-01T00:00:00+00:00",
                     "这一行根本不是 JSON", None))
    rc, text = _run(db, "--project", P, "--json")
    assert rc == 0, text
    payload = _payload(text)
    assert payload["total"] == 2, payload
    assert payload["unparseable_rows"] == 1, payload

    rc2, prose = _run(db, "--project", P)
    assert rc2 == 0, prose
    assert "legacy.import" in prose and "比不了值" in prose, prose
    assert "1 条的 before/after" in prose, prose

    # 脏行 + `--record` 一起用才是这条例外的原告：没有 json_valid 兜底，SQLite 会在整条
    # 查询上抛 malformed JSON；只跑不带 record 的查询永远碰不到那段谓词（电池 B3 首轮
    # SURVIVED 就是这么露出来的）。记录号取自权威表，不在测试里重解析 payload。
    newest = _latest(db, P)
    rc3, withrecord = _run(db, "--project", P, "--record", newest, "--json")
    assert rc3 == 0, withrecord
    hit = _payload(withrecord)
    assert hit["total"] == 1 and hit["returned"] == 1, hit
    assert hit["unparseable_rows"] == 1, hit


def test_since_normalizes_timezones_and_filters(env) -> None:
    db = env
    _one_change(db, P, "hole_a", "TOP.a1")
    rc, future = _run(db, "--project", P, "--since", "2099-01-01T00:00:00Z", "--json")
    assert rc == 0, future
    assert _payload(future)["total"] == 0, future
    rc2, past = _run(db, "--project", P, "--since", "2000-01-01", "--json")
    assert rc2 == 0, past
    assert _payload(past)["total"] == 1, past
    # 手工钉一行时间戳恰好等于下界的审计行：不做 UTC 归一时，'…Z' 按字符串比会
    # **大于** '…+00:00'，同一瞬间的这一行就被漏掉
    edge = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(str(db)) as con:
        con.execute("INSERT INTO audit_log(actor,action,project_id,tenant_id,timestamp,"
                    "before_json,after_json) VALUES(?,?,?,?,?,?,?)",
                    ("潘工", "ctq.revise", P, T, edge, None, None))
    rc_z, withz = _run(db, "--project", P, "--since", "2026-01-01T00:00:00Z", "--json")
    assert rc_z == 0, withz
    payload = _payload(withz)
    assert payload["filters"]["since"] == edge, payload
    assert payload["entries"][0]["timestamp"] == edge, payload
    rc3, bad = _run(db, "--project", P, "--since", "不是时间")
    assert rc3 == 2, bad
    assert "ISO 8601" in bad, bad


def test_changed_values_are_rendered_not_just_field_names(env) -> None:
    """只报「改了 upper_limit」不够——registry 那句限制的原文是要人自己按 JSON 筛值。"""
    db = env
    rid = _add(db, P, "hole_a", "TOP.a1")
    assert _revise(db, P, rid, "8.10") == 0
    rc, text = _run(db, "--project", P)
    assert rc == 0, text
    assert "upper_limit: 8.05 → 8.1" in text, text
    assert "declared_by: 潘工 → 张工" in text, text
    # 记录号/时间戳这类每行必变的噪声不进改动清单
    assert "record_id:" not in text, text


def test_listing_writes_no_audit_row(env) -> None:
    db = env
    rid = _add(db, P, "hole_a", "TOP.a1")
    before = len(AIPDStateDB(str(db)).list_audit(limit=500))
    rc, text = _run(db, "--project", P, "--json")
    assert rc == 0, text
    assert len(AIPDStateDB(str(db)).list_audit(limit=500)) == before, \
        "查看一次就在审计里留一行，「谁改了事实」再也问不出来"
    assert _revise(db, P, rid, "8.10") == 0
    after = len(AIPDStateDB(str(db)).list_audit(limit=500))
    assert after > before, "反向对照不成立：写命令也没留审计行，上一条断言就是空的"


def test_failure_paths退2_and_emit_no_success_payload(env, tmp_path) -> None:
    missing = tmp_path / "not-here.db"
    rc, text = _run(missing, "--project", P)
    assert rc == 2, text
    assert "0 条" not in text, text
    rc2, text2 = _run(missing, "--project", P, "--json")
    assert rc2 == 2, text2
    assert '"ok": true' not in text2, text2


def test_action_filter_is_exact_not_a_prefix_glob(env) -> None:
    """动作名里本来就有 `.`（`ctq.add` / `ctq.revise`）：做前缀通配会把
    `--action ctq` 变成另一个查询，所以只给精确匹配 + 可重复。"""
    db = env
    _one_change(db, P, "hole_a", "TOP.a1")
    assert _deprecate(db, P, _latest(db, P)) == 0
    rc, only_revise = _run(db, "--project", P, "--action", "ctq.revise", "--json")
    assert rc == 0, only_revise
    payload = _payload(only_revise)
    assert [e["action"] for e in payload["entries"]] == ["ctq.revise"], payload
    assert payload["total"] == 1, payload
    rc2, glob = _run(db, "--project", P, "--action", "ctq", "--json")
    assert rc2 == 0, glob
    assert _payload(glob)["total"] == 0, _payload(glob)
    rc3, both = _run(db, "--project", P, "--action", "ctq.revise",
                     "--action", "ctq.deprecate", "--json")
    assert rc3 == 0, both
    assert _payload(both)["total"] == 2, both
    # 声明本身不写审计行：这张读面看不到「谁第一次声明」，那是写入侧的一格
    rc4, created = _run(db, "--project", P, "--action", "ctq.add", "--json")
    assert rc4 == 0 and _payload(created)["total"] == 0, created


def test_readme_quickref_lists_the_new_command(env) -> None:
    lines = [ln.strip() for ln in README.read_text(encoding="utf-8").splitlines()]
    assert any(ln.startswith("aipd truth history") for ln in lines), \
        "README 要有行首可执行的 `aipd truth history …` 这一行"
