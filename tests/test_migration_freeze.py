"""v5.8.1 Commit 8：Migration freeze / schema authority 测试。

覆盖：
- v1 冻结：V1_FROZEN_SHA256 防漂移 + migrations.py 不 import db.SCHEMA（AST 检查）；
- 旧库升级：v1-era（17 表）/ v2-era / v3-era 数据全保留 → migrate → 最新 schema；
- schema authority：AIPDStateDB 新建库后 schema_migrations 记录 v1..v5 全链
  （migration runner 是唯一建库路径，无 SCHEMA 旁路执行痕迹）。
"""
from __future__ import annotations

import ast
import hashlib
import sqlite3

from aipd_os.state import migrations as mig
from aipd_os.state.db import SCHEMA, AIPDStateDB


def _tables(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


# ---------------------------------------------------------------------------
# 1) v1 冻结
# ---------------------------------------------------------------------------
def test_frozen_v1_schema_does_not_drift():
    """V1 文本 hash 与冻结常量一致；migrations.py 不再 import db.SCHEMA。"""
    # hash 冻结校验
    assert hashlib.sha256(mig.V1_INITIAL_SCHEMA.encode("utf-8")).hexdigest() == \
        mig.V1_FROZEN_SHA256
    assert mig._v1_frozen_sha256() == mig.V1_FROZEN_SHA256
    # v1 文本确实是 17 张基础表（不含 ideas/claims/relations/id_sequences）
    for t in ("tenants", "users", "user_access", "sessions", "projects", "facts",
              "evidence", "fact_evidence", "decisions", "deliverables",
              "dependencies", "risks", "changes", "gates", "audit_log",
              "checkpoints", "backups"):
        assert f"CREATE TABLE IF NOT EXISTS {t}" in mig.V1_INITIAL_SCHEMA
    for t in ("ideas", "claims", "claim_evidence_relations", "id_sequences"):
        assert f"CREATE TABLE IF NOT EXISTS {t}" not in mig.V1_INITIAL_SCHEMA
    # AST 检查：migrations.py 不 import db.SCHEMA（不 import .db 的 SCHEMA 名字）
    with open(mig.__file__, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            if node.module and "db" in node.module and "SCHEMA" in names:
                raise AssertionError("migrations.py 不得 import db.SCHEMA（v1 未冻结）")
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "SCHEMA" or (a.name.endswith(".db")):
                    raise AssertionError("migrations.py 不得 import db.SCHEMA（v1 未冻结）")
    # v1 文本与 db.SCHEMA 的 17 表部分一致（参考快照）
    assert "CREATE TABLE IF NOT EXISTS ideas" not in mig.V1_INITIAL_SCHEMA


# ---------------------------------------------------------------------------
# 2) 旧库升级到最新（数据保留）
# ---------------------------------------------------------------------------
def test_old_database_migrates_to_latest(tmp_path):
    """v1-era 库（仅 17 表）→ migrate → 最新 schema 可用且旧数据保留。"""
    path = str(tmp_path / "old.db")
    # 构造 v1-era：只保留 version<=1
    mig.migrate(path)
    mig.rollback(path, target=1)  # 回滚 v5..v2，只剩 v1
    assert mig.current_version(path) == 1
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO tenants(tenant_id, name, created_at) "
                 "VALUES('default','T','2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO projects(project_id,tenant_id,name,goal,gate,status,"
                 "version,owner_policy,created_at,updated_at,version_no) "
                 "VALUES('p1','default','P1','g','G1','active','1.0','AI',"
                 "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',1)")
    conn.commit()
    conn.close()
    assert "ideas" not in _tables(sqlite3.connect(path))

    applied = mig.migrate(path)
    assert applied == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    tables = _tables(conn)
    # 数据保留
    assert conn.execute("SELECT name FROM projects").fetchone()["name"] == "P1"
    assert conn.execute("SELECT name FROM tenants").fetchone()["name"] == "T"
    conn.close()
    for t in ("ideas", "claims", "claim_evidence_relations", "id_sequences"):
        assert t in tables
    # 最新 schema 可用
    db = AIPDStateDB(path)
    db.ensure_default_tenant("default")
    assert db.get_project("default", "p1")["name"] == "P1"
    assert mig.current_version(path) == 15


def test_v2_v3_era_db_data_preserved(tmp_path):
    """v2/v3-era 库升级到最新：ideas/claims 数据保留。"""
    path = str(tmp_path / "era.db")
    mig.migrate(path)
    # 回滚到 v2（保留 v1+v2：tenants..ideas）
    mig.rollback(path, target=2)
    assert mig.current_version(path) == 2
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO tenants(tenant_id, name, created_at) "
                 "VALUES('default','T','2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO ideas(idea_id,project_id,tenant_id,title,raw_input,"
                 "goal,problem,target_user,desired_outcome,constraints_json,source,"
                 "lifecycle_status,version_no,created_at,updated_at) "
                 "VALUES('IDEA-001','p1','default','t','r','','','','','{}','',"
                 "'active',1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
    conn.commit()
    conn.close()

    applied = mig.migrate(path)
    assert applied == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    idea = conn.execute("SELECT * FROM ideas WHERE idea_id='IDEA-001'").fetchone()
    assert idea is not None and idea["title"] == "t"
    conn.close()


# ---------------------------------------------------------------------------
# 3) schema authority：migration runner 是唯一 authority
# ---------------------------------------------------------------------------
def test_migration_runner_is_schema_authority(tmp_path):
    """AIPDStateDB 新建库后 schema_migrations 记录 v1..v5 全链（无 SCHEMA 旁路）。"""
    path = str(tmp_path / "fresh.db")
    AIPDStateDB(path)
    conn = sqlite3.connect(path)
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version")]
    tables = _tables(conn)
    conn.close()
    # 全链 v1..v8 都通过 migration runner 应用
    assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    assert "schema_migrations" in tables
    # SCHEMA 常量只是参考，__init__ 不再 executescript(SCHEMA)：
    # 新建库的表集合应等于迁移全链产物（含 id_sequences）
    for t in ("tenants", "ideas", "claims", "claim_evidence_relations",
              "id_sequences", "schema_migrations"):
        assert t in tables
    # 幂等：再次打开不重复应用
    AIPDStateDB(path)
    assert mig.migrate(path) == []
    # SCHEMA 参考仍可解析（保持可用）
    assert "CREATE TABLE IF NOT EXISTS ideas" in SCHEMA
