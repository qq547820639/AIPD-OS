"""DB 迁移 / 备份恢复兼容性测试。

覆盖：
- 迁移运行器：migrate 应用全部版本、幂等、current_version；
- 回滚到目标版本；
- 备份 / 恢复兼容性：备份→变更→恢复后数据一致；
- 恢复前校验和校验（损坏备份拒绝恢复）；
- 跨迁移的备份恢复：先迁移到当前 schema，再备份 / 恢复保持数据一致。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.state import migrations as mig
from aipd_os.state.backup import BackupManager
from aipd_os.state.db import AIPDStateDB


def _seed(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    db.add_fact("default", "p1", "latency", 42, "V")
    db.add_fact("default", "p1", "accuracy", 0.9, "V")


def test_migrate_applies_all_versions_and_records(tmp_path):
    path = str(tmp_path / "state.db")
    applied = mig.migrate(path)
    assert applied == [mig.MIGRATIONS[-1]["version"]]
    assert mig.current_version(path) == mig.MIGRATIONS[-1]["version"]
    assert mig.applied_versions(path) == applied


def test_migrate_is_idempotent(tmp_path):
    path = str(tmp_path / "state.db")
    mig.migrate(path)
    assert mig.migrate(path) == []  # 二次迁移无新版本
    assert len(mig.applied_versions(path)) == len(mig.MIGRATIONS)


def test_migrate_can_apply_on_existing_data(tmp_path):
    """兼容性：已含数据的库再执行迁移不丢数据。"""
    path = str(tmp_path / "state.db")
    mig.migrate(path)
    db = AIPDStateDB(path)
    _seed(db)
    del db
    # 再次迁移（幂等），数据应保留
    assert mig.migrate(path) == []
    db2 = AIPDStateDB(path)
    assert len(db2.list_facts("default", "p1")) == 2
    assert db2.get_project("default", "p1")["name"] == "P1"


def test_rollback_to_zero_drops_schema(tmp_path):
    path = str(tmp_path / "state.db")
    mig.migrate(path)
    db = AIPDStateDB(path)
    _seed(db)
    del db
    rolled = mig.rollback(path, target=0)
    assert rolled == [mig.MIGRATIONS[-1]["version"]]
    assert mig.current_version(path) == 0
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'").fetchall()
    conn.close()
    assert rows == []  # 业务表已回滚删除


def test_backup_restore_preserves_data(tmp_path):
    path = str(tmp_path / "state.db")
    db = AIPDStateDB(path)
    _seed(db)
    bm = BackupManager(path, backup_dir=str(tmp_path / "backups"))
    backup = bm.create_backup(path)

    # 继续写入更多数据
    db.add_fact("default", "p1", "third", 7, "V")
    assert len(db.list_facts("default", "p1")) == 3
    del db

    restored = str(tmp_path / "restored.db")
    bm.restore_backup(backup, restored)
    rdb = AIPDStateDB(restored)
    facts = {f["key"]: f["value"] for f in rdb.list_facts("default", "p1")}
    assert facts == {"latency": 42, "accuracy": 0.9}  # 恢复后回到备份时刻


def test_restore_rejects_corrupted_backup(tmp_path):
    path = str(tmp_path / "state.db")
    db = AIPDStateDB(path)
    _seed(db)
    del db
    bm = BackupManager(path, backup_dir=str(tmp_path / "backups"))
    backup = bm.create_backup(path)

    # 篡改备份数据库文件 → restore 应因 checksum 不一致而拒绝
    import glob
    db_file = glob.glob(str(backup) + "/*.db")[0]
    with open(db_file, "ab") as fh:
        fh.write(b"CORRUPTED")
    with pytest.raises(ValueError, match="checksum mismatch"):
        bm.restore_backup(backup, str(tmp_path / "restored2.db"))


def test_backup_restore_after_migration_compatible(tmp_path):
    """迁移到当前 schema 后再备份 / 恢复，兼容性保持。"""
    path = str(tmp_path / "state.db")
    mig.migrate(path)
    db = AIPDStateDB(path)
    _seed(db)
    db.resolve_decision("default", "p1", db.propose_decision(
        "default", "p1", "pick model", "use A", ["A", "B"]), "A", "go")
    del db

    bm = BackupManager(path, backup_dir=str(tmp_path / "backups"))
    backup = bm.create_backup(path)

    restored = str(tmp_path / "restored.db")
    bm.restore_backup(backup, restored)

    # 恢复库仍可正常迁移（schema_migrations 表随文件一起备份）
    assert mig.migrate(restored) == []
    rdb = AIPDStateDB(restored)
    assert len(rdb.list_facts("default", "p1")) == 2
    assert len(rdb.list_decisions("default", "p1")) == 1