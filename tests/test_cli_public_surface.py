"""F-CLI-COV 第 40 片：把登记在册的 17 条命令补成**走过 CLI 入口**的常驻用例。

第 39 片修好量具后量出的缺口是：66 条注册命令里 17 条低于 `cli` 档
（10 条零证据、4 条只被 deprecated 别名走过、1 条只被直接调处理函数走过、
2 条调的是被两条命令共用的 `cmd_outbox`）。本片把它们全部补成
`main([...])` 形态——**走 argparse、走分发**，而不是再直接调 `cmd_*`：
F-CLI-01 已经证过真正的产品面是解析器，直接调处理函数看不见接线缺失。

断言一律落在**读数**上（JSON 字段、退出码、落盘产物），不是「rc 不为 0 就算跑过」——
第 33 片量过那种写法分不清「门在拦」和「门永远红」。所以每条都同时钉：
走得到（rc 与产物）+ 该拦的拦得住（`cad build` 在 faceted_brep 封顶 C1 时目标 C1
仍判不过 ⇒ rc=4，这是门禁在拦，不是没接线）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.cli import commands_release
from aipd_os.cli import main as cli_main


def _out(capsys) -> str:
    text: str = capsys.readouterr().out
    return text


def _json_out(capsys) -> dict:
    out = _out(capsys).strip().splitlines()[-1]
    data: dict = json.loads(out)
    return data


@pytest.fixture
def db(tmp_path) -> Path:
    path: Path = tmp_path / "state.db"
    assert cli_main.main(["init", "--db", str(path), "--project", "p1",
                          "--name", "外骨骼项目", "--goal", "评估助力系统"]) == 0
    return path


def _manifest(tmp_path) -> Path:
    """faceted_brep 运行时：成熟度封顶 C1，用于钉「门禁在拦」。"""
    m: Path = tmp_path / "manifest.json"
    m.write_text(json.dumps({"runtime": "faceted_brep", "evidence": {}}), encoding="utf-8")
    return m


# ---------------------------------------------------------------- version / doctor

def test_version_json_reports_package_version(tmp_path, capsys) -> None:
    assert cli_main.main(["version", "--json"]) == 0
    data = _json_out(capsys)
    assert data["command"] == "version"
    assert data["version"], "版本号读空 ⇒ aipd version 等于没打印任何东西"


def test_doctor_via_cli_reports_all_check_groups(capsys) -> None:
    """doctor 从前只有 cmd_doctor(...) 直调的记录；这里走 argv 位并核检查项分组。"""
    assert cli_main.main(["doctor", "--json"]) == 0
    data = _json_out(capsys)
    assert data["ok"] is True
    names = {c["name"] for c in data["checks"]}
    groups = {n.split(".")[0] for n in names}
    assert {"dependency", "capability", "database", "security"} <= groups, sorted(groups)


# ---------------------------------------------------------------- cad preflight / build

def test_cad_preflight_passes_at_the_runtime_ceiling(tmp_path, capsys) -> None:
    """cad preflight 只问「运行时上限允不允许这个目标」⇒ faceted_brep 问 C1 应当放行。"""
    assert cli_main.main(["cad", "preflight", "--manifest", str(_manifest(tmp_path)),
                          "--target", "C1", "--json"]) == 0
    data = _json_out(capsys)
    assert data["command"] == "cad preflight"
    assert data["runtime_ceiling"] == "C1" and data["faceted_brep_capped"] is True
    assert data["passed"] is True and data["target_passed"] is False, \
        "preflight 该判「上限允许」，把 build 的 reached_level 判据混进来就分不清两问了"


def test_cad_build_refuses_capped_runtime_with_rc4(tmp_path, capsys) -> None:
    """同一份 manifest 问 build：封顶 C1 ⇒ 目标未达成，退 4（门禁在拦，不是没接线）。"""
    rc = cli_main.main(["cad", "build", "--manifest", str(_manifest(tmp_path)),
                        "--target", "C1", "--json"])
    data = _json_out(capsys)
    assert rc == 4, f"cad build 应当以 4 拒绝封顶运行时，实得 rc={rc}"
    assert data["ok"] is False and data["target_passed"] is False
    assert data["reached_level"] is None, "没有证据却报出 reached_level ⇒ 门禁在虚构达成度"


# ---------------------------------------------------------------- 所有者体验面

def test_onboard_creates_a_project_and_first_result(tmp_path, capsys) -> None:
    db = tmp_path / "ob.db"
    assert cli_main.main(["onboard", "--db", str(db), "--project", "p-ob",
                          "--idea", "做一款更轻的外骨骼", "--json"]) == 0
    data = _json_out(capsys)
    assert data["project_id"] == "p-ob"
    kinds = {p["kind"] for p in data["produced"]}
    assert {"fact", "risk", "deliverable", "decision"} <= kinds, sorted(kinds)
    assert data["first_result"]["details"]["counts"]["open_risks"] == 1


def test_dashboard_json_exposes_all_owner_blocks(db, capsys) -> None:
    assert cli_main.main(["dashboard", "--db", str(db), "--project", "p1",
                          "--json"]) == 0
    data = _json_out(capsys)
    assert {"current_goal", "executing", "missing", "top_risk", "health",
            "risk_ownership"} <= set(data), sorted(data)
    # 空台账的措辞必须是「暂无风险条目」，不是「0 条风险都有真人认领」
    assert data["risk_ownership"]["summary"] == "暂无风险条目"


def test_operate_runs_the_intent_loop_to_done(db, capsys) -> None:
    assert cli_main.main(["operate", "--db", str(db), "--project", "p1",
                          "--intent", "成本降低20%", "--json"]) == 0
    data = _json_out(capsys)
    assert data["status"] == "done"
    steps = [p["step"] for p in data["progress"]]
    assert steps == ["intent", "impact", "rework", "acceptance", "summary", "done"], steps
    assert data["impact"]["reversible"] is True


def test_reset_then_recover_from_its_backup(tmp_path, capsys) -> None:
    """reset 的备份目录必须真能被 recover 吃回去——两个命令配成一对手感。"""
    db = tmp_path / "rs.db"
    assert cli_main.main(["init", "--db", str(db), "--project", "p-r",
                          "--name", "重置演练", "--goal", "验证备份"]) == 0
    capsys.readouterr()
    assert cli_main.main(["reset", "--db", str(db), "--project", "p-r", "--json"]) == 0
    reset = _json_out(capsys)
    assert reset["ok"] is True and reset["command"] == "reset"
    backup = Path(reset["backup"])
    assert backup.exists(), f"reset 报了备份目录 {backup} 但盘上没有"
    assert cli_main.main(["recover", "--db", str(db), "--project", "p-r",
                          "--backup", str(backup), "--json"]) == 0
    recovered = _json_out(capsys)
    assert recovered["ok"] is True and recovered["command"] == "recover"


def test_recover_without_backup_rolls_back_via_revert(db, capsys) -> None:
    """不带 --backup 时走的是「回滚最近可撤销操作」那条分支，不是备份恢复。"""
    assert cli_main.main(["recover", "--db", str(db), "--project", "p1",
                          "--json"]) == 0
    data = _json_out(capsys)
    assert data["ok"] is True and data["project_id"] == "p1"
    assert "restored" not in data, "没给 --backup 却报「已恢复备份」⇒ 两条分支被混成一谈"


def test_ui_wires_db_host_port_into_the_server(tmp_path, capsys, monkeypatch) -> None:
    """ui 的产品面是「把参数交给服务器」；起真服务会挂住套件，所以只 mock 那一层。"""
    import aipd_os.web as web

    seen: dict[str, object] = {}

    def fake_serve(console, host=None, port=None):
        seen["host"], seen["port"] = host, port
        seen["db"] = console.db_path
        return None

    monkeypatch.setattr(web, "serve", fake_serve)
    assert cli_main.main(["ui", "--db", str(tmp_path / "ui.db"), "--host", "127.0.0.1",
                          "--port", "8123"]) == 0
    assert seen == {"host": "127.0.0.1", "port": 8123,
                    "db": str(tmp_path / "ui.db")}, f"serve 收到的参数：{seen}"


# ---------------------------------------------------------------- 产品定义面

def test_product_show_projects_an_empty_definition(db, capsys) -> None:
    assert cli_main.main(["product", "show", "--db", str(db), "--project", "p1",
                          "--json"]) == 0
    data = _json_out(capsys)
    assert data["project_id"] == "p1"
    assert data["counts"]["insights"] == 0 and data["features"] == []
    assert set(data["gate"]) == {"snapshot", "technical", "authorization", "eligibility"}


def test_product_gate_without_snapshot_says_no_snapshot(db, capsys) -> None:
    assert cli_main.main(["product", "gate", "--db", str(db), "--project", "p1",
                          "--json"]) == 0
    data = _json_out(capsys)
    assert data["technical"]["result"] == "NO_SNAPSHOT"
    assert data["eligibility"] == {"eligible": False, "reason": "no snapshot"}
    assert data["authorization"]["state"] == "PENDING", "AI 不能替属主先把门禁置成已批"


# ---------------------------------------------------------------- outbox 两个 verb

def test_outbox_drain_and_review_are_distinct_verbs(db, capsys) -> None:
    """从前两条命令共调 cmd_outbox，量具分不清 verb；这里各走一次 argv。"""
    assert cli_main.main(["outbox", "drain", "--db", str(db), "--json"]) == 0
    drain = _json_out(capsys)
    assert drain["command"].startswith("outbox"), drain
    assert cli_main.main(["outbox", "review", "--db", str(db), "--json"]) == 0
    review = _json_out(capsys)
    assert review["command"].startswith("outbox"), review
    assert review != drain, "drain 与 review 读数字节相同 ⇒ 第二个 verb 其实没被分发"


# ---------------------------------------------------------------- 公开名而非别名

def test_public_names_work_not_only_the_deprecated_aliases(tmp_path, capsys,
                                                           monkeypatch) -> None:
    """cad build / package / resume / test 四条从前只有 deprecated 别名被走过。

    这里按**公开名**走：`resume` 用 argv，`test`/`package` 会真跑套件与打包，
    所以把它们下面那层重活换掉（仍经过 argparse 与分发）。
    """
    monkeypatch.setattr(commands_release, "_run_pytest", lambda repo: 0)
    monkeypatch.setattr(commands_release, "_build_release_impl", lambda args: 0)

    assert cli_main.main(["test", "--json"]) == 0
    assert _json_out(capsys) == {"command": "test", "ok": True, "exit_code": 0}

    out = tmp_path / "rel"
    assert cli_main.main(["package", "--version", "9.9.9", "--out", str(out),
                          "--no-tests", "--json"]) == 0
    packaged = _json_out(capsys)
    assert packaged["command"] == "package" and packaged["ok"] is True

    db = tmp_path / "rs2.db"
    assert cli_main.main(["init", "--db", str(db), "--project", "p-r2",
                          "--name", "别名对照", "--goal", "验证公开名"]) == 0
    capsys.readouterr()
    assert cli_main.main(["resume", "--db", str(db), "--json"]) == 0
    resumed = _json_out(capsys)
    assert resumed["command"] == "resume" and resumed["project_id"] == "p-r2"
    assert resumed["restored_from"] is None

    rc = cli_main.main(["cad", "build", "--manifest", str(_manifest(tmp_path)),
                        "--target", "C6", "--json"])
    built = _json_out(capsys)
    assert rc == 4 and built["command"] == "cad build", "公开名 cad build 必须真被分发"
