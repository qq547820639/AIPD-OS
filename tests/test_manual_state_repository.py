"""P2-M4: Manual State Repository tests。

验证 manual_workflows 表 canonical state 读写 + legacy JSON 导入。
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from aipd_os.state.manual_state import ManualStateRepository


@pytest.fixture
def conn(tmp_path):
    """创建带 v16 schema 的临时数据库。"""
    from aipd_os.state import migrations as mig
    path = str(tmp_path / "test.db")
    mig.migrate(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


@pytest.fixture
def repo(conn):
    return ManualStateRepository(conn)


@pytest.fixture
def legacy_json(tmp_path):
    """创建 legacy manual JSON。"""
    data = {
        "project_id": "P-1",
        "batch_plan": [{"batch_id": "B1", "pages": 10}],
        "pages": [],
    }
    path = tmp_path / "legacy.manual.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestCanonicalReadWrite:
    """canonical 读写。"""

    def test_write_and_read(self, repo, conn):
        state = {"key": "value", "batch_plan": []}
        version = repo.write("T-A", "P-1", "wf-1", state)
        assert version == 1
        conn.commit()
        result = repo.read("T-A", "P-1", "wf-1")
        assert result is not None
        assert result["key"] == "value"
        assert result["_tenant_id"] == "T-A"
        assert result["_project_id"] == "P-1"
        assert result["_version_no"] == 1

    def test_read_nonexistent(self, repo):
        assert repo.read("T-A", "P-1", "nonexistent") is None

    def test_optimistic_concurrency(self, repo, conn):
        """两个 writer 同一 version → 一个失败。"""
        state = {"key": "value"}
        v = repo.write("T-A", "P-1", "wf-1", state)
        conn.commit()
        repo.write("T-A", "P-1", "wf-1", {"key": "B"}, expected_version=v)
        conn.commit()
        with pytest.raises(ValueError, match="ConcurrentModification"):
            repo.write("T-A", "P-1", "wf-1", {"key": "A"}, expected_version=v)

    def test_update_increments_version(self, repo, conn):
        v1 = repo.write("T-A", "P-1", "wf-1", {"step": 1})
        conn.commit()
        v2 = repo.write("T-A", "P-1", "wf-1", {"step": 2},
                         expected_version=v1)
        conn.commit()
        assert v2 == 2
        result = repo.read("T-A", "P-1", "wf-1")
        assert result["_version_no"] == 2


class TestLegacyImport:
    """legacy JSON 导入。"""

    def test_import_from_legacy(self, repo, conn, legacy_json):
        result = repo.import_from_legacy("T-A", "P-1", "wf-1", legacy_json)
        conn.commit()
        assert result["status"] == "IMPORTED"
        state = repo.read("T-A", "P-1", "wf-1")
        assert state is not None
        assert state["_tenant_id"] == "T-A"
        assert state["_project_id"] == "P-1"

    def test_import_idempotent(self, repo, conn, legacy_json):
        """相同内容重复导入应为 NO_OP。"""
        repo.import_from_legacy("T-A", "P-1", "wf-1", legacy_json)
        conn.commit()
        result = repo.import_from_legacy("T-A", "P-1", "wf-1", legacy_json)
        assert result["status"] == "NO_OP"

    def test_import_conflict_without_force(self, repo, conn, legacy_json):
        """canonical 已存在且内容不同时应 CONFLICT。"""
        repo.write("T-A", "P-1", "wf-1", {"different": "content"})
        conn.commit()
        result = repo.import_from_legacy("T-A", "P-1", "wf-1", legacy_json)
        assert result["status"] == "CONFLICT"

    def test_import_force_overwrites(self, repo, conn, legacy_json):
        """force=True 应覆盖 canonical。"""
        repo.write("T-A", "P-1", "wf-1", {"different": "content"})
        conn.commit()
        result = repo.import_from_legacy("T-A", "P-1", "wf-1", legacy_json,
                                          force=True)
        conn.commit()
        assert result["status"] == "IMPORTED"
        state = repo.read("T-A", "P-1", "wf-1")
        assert "batch_plan" in state

    def test_import_nonexistent_file(self, repo):
        with pytest.raises(FileNotFoundError):
            repo.import_from_legacy("T-A", "P-1", "wf-1", "/nonexistent.json")


class TestExport:
    """导出（projection, not truth）。"""

    def test_export_to_json(self, repo, conn, tmp_path):
        repo.write("T-A", "P-1", "wf-1", {"key": "value"})
        conn.commit()
        export_path = tmp_path / "export.json"
        repo.export_to_json("T-A", "P-1", "wf-1", export_path)
        data = json.loads(export_path.read_text(encoding="utf-8"))
        assert data["_export_type"] == "projection"
        assert data["key"] == "value"

    def test_export_nonexistent(self, repo, tmp_path):
        with pytest.raises(FileNotFoundError):
            repo.export_to_json("T-A", "P-1", "nonexistent",
                                tmp_path / "export.json")


class TestTenantScope:
    """tenant/project scope 注入。"""

    def test_scope_injected_on_write(self, repo, conn):
        repo.write("T-A", "P-1", "wf-1", {"data": "test"})
        conn.commit()
        state = repo.read("T-A", "P-1", "wf-1")
        assert state["_tenant_id"] == "T-A"
        assert state["_project_id"] == "P-1"

    def test_different_scopes_isolated(self, repo, conn):
        repo.write("T-A", "P-1", "wf-1", {"data": "A"})
        repo.write("T-B", "P-2", "wf-1", {"data": "B"})
        conn.commit()
        state_a = repo.read("T-A", "P-1", "wf-1")
        state_b = repo.read("T-B", "P-2", "wf-1")
        assert state_a["data"] == "A"
        assert state_b["data"] == "B"
        assert repo.read("T-A", "P-2", "wf-1") is None
