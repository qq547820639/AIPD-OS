"""备份：创建/恢复/保留清理；检查点保存/恢复；恢复摘要不重复追问已解决决策。"""
from __future__ import annotations

import json

import pytest

from aipd_os.state.backup import BackupManager
from aipd_os.state.checkpoint import CheckpointManager
from aipd_os.state.db import AIPDStateDB


@pytest.fixture
def db(tmp_path):
    return AIPDStateDB(str(tmp_path / "state.db"), encryption_key="k")


def _seed(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    db.add_fact("default", "p1", "latency", 42, "V")


def test_create_restore(tmp_path, db):
    _seed(db)
    bm = BackupManager(str(db.path), backup_dir=str(tmp_path / "backups"))
    backup = bm.create_backup(str(db.path))

    # 继续写入，数量变多
    db.add_fact("default", "p1", "accuracy", 0.9, "V")
    assert len(db.list_facts("default", "p1")) == 2

    # 恢复到新路径，应回到备份时的状态
    restored = str(tmp_path / "restored.db")
    bm.restore_backup(backup, restored)
    rdb = AIPDStateDB(restored)
    assert len(rdb.list_facts("default", "p1")) == 1


def test_retention_prune(tmp_path, db):
    _seed(db)
    bm = BackupManager(str(db.path), backup_dir=str(tmp_path / "backups"))
    bm.create_backup(str(db.path))
    bm.create_backup(str(db.path))
    assert len(bm.list_backups()) == 2

    # 把所有备份的 manifest 时间改成旧时间，触发保留清理
    for b in bm.list_backups():
        mf = json.loads((__import__("pathlib").Path(b["backup_dir"]) / "manifest.json").read_text())
        mf["backup_created_at"] = "2020-01-01T00:00:00+00:00"
        (__import__("pathlib").Path(b["backup_dir"]) / "manifest.json").write_text(
            json.dumps(mf), encoding="utf-8")

    removed = bm.retention_prune(bm.list_backups(), retention_days=30)
    assert len(removed) == 2
    assert bm.list_backups() == []


def test_checkpoint_save_restore(db):
    _seed(db)
    cm = CheckpointManager(db)
    cm.save_checkpoint("p1", {"facts_seen": 1, "note": "phase G1"}, summary={"phase": "G1"})
    cp = cm.restore_latest("p1")
    assert cp["data"]["note"] == "phase G1"
    assert cp["summary"]["phase"] == "G1"


def test_resume_summary_does_not_relist_resolved_decisions(db):
    _seed(db)
    cm = CheckpointManager(db)
    did = db.propose_decision("default", "p1", "pick model", "use A", ["A", "B"])
    db.resolve_decision("default", "p1", did, "A", "go")
    cm.save_checkpoint("p1", {"state": "after decision"}, summary={"note": "decided"})

    summary = cm.resume_summary("p1")
    assert did in summary["resolved_decision_ids"]
    assert [d["decision_id"] for d in summary["pending_decisions"]] == []
    # 已解决决策不应再出现在待办/需追问列表
    assert sum(1 for d in summary["pending_decisions"] if d["decision_id"] == did) == 0
    assert summary["next_action"] == "continue phase G0"
