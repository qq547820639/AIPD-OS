"""P2-M4: Manual State Repository tests。

验证 legacy JSON 导入到 canonical state 的行为。
"""
from __future__ import annotations

import json

import pytest

from aipd_os.state.manual_state import ManualStateRepository


@pytest.fixture
def repo(tmp_path):
    return ManualStateRepository(
        tmp_path / "canonical",
        tenant_id="T-A",
        project_id="P-1",
    )


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

    def test_write_and_read(self, repo):
        state = {"key": "value", "batch_plan": []}
        repo.write("wf-1", state)
        result = repo.read("wf-1")
        assert result is not None
        assert result["key"] == "value"
        assert result["_tenant_id"] == "T-A"
        assert result["_project_id"] == "P-1"
        assert "_updated_at" in result

    def test_read_nonexistent(self, repo):
        assert repo.read("nonexistent") is None


class TestLegacyImport:
    """legacy JSON 导入。"""

    def test_import_from_legacy(self, repo, legacy_json):
        result = repo.import_from_legacy("wf-1", legacy_json)
        assert result["status"] == "IMPORTED"
        # 验证 canonical state
        state = repo.read("wf-1")
        assert state is not None
        assert state["_tenant_id"] == "T-A"
        assert state["_project_id"] == "P-1"

    def test_import_idempotent(self, repo, legacy_json):
        """相同内容重复导入应为 NO_OP。"""
        repo.import_from_legacy("wf-1", legacy_json)
        result = repo.import_from_legacy("wf-1", legacy_json)
        assert result["status"] == "NO_OP"

    def test_import_conflict_without_force(self, repo, legacy_json):
        """canonical 已存在且内容不同时应 CONFLICT。"""
        repo.write("wf-1", {"different": "content"})
        result = repo.import_from_legacy("wf-1", legacy_json)
        assert result["status"] == "CONFLICT"

    def test_import_force_overwrites(self, repo, legacy_json):
        """force=True 应覆盖 canonical。"""
        repo.write("wf-1", {"different": "content"})
        result = repo.import_from_legacy("wf-1", legacy_json, force=True)
        assert result["status"] == "IMPORTED"
        state = repo.read("wf-1")
        assert "batch_plan" in state

    def test_import_nonexistent_file(self, repo):
        with pytest.raises(FileNotFoundError):
            repo.import_from_legacy("wf-1", "/nonexistent/path.json")


class TestExport:
    """导出（projection, not truth）。"""

    def test_export_to_json(self, repo, tmp_path):
        repo.write("wf-1", {"key": "value"})
        export_path = tmp_path / "export.json"
        repo.export_to_json("wf-1", export_path)
        data = json.loads(export_path.read_text(encoding="utf-8"))
        assert data["_export_type"] == "projection"
        assert data["key"] == "value"

    def test_export_nonexistent(self, repo, tmp_path):
        with pytest.raises(FileNotFoundError):
            repo.export_to_json("nonexistent", tmp_path / "export.json")


class TestTenantScope:
    """tenant/project scope 注入。"""

    def test_scope_injected_on_write(self, repo):
        repo.write("wf-1", {"data": "test"})
        state = repo.read("wf-1")
        assert state["_tenant_id"] == "T-A"
        assert state["_project_id"] == "P-1"

    def test_different_repos_different_scope(self, tmp_path):
        repo_a = ManualStateRepository(tmp_path / "canon", "T-A", "P-1")
        repo_b = ManualStateRepository(tmp_path / "canon", "T-B", "P-2")
        repo_a.write("wf-1", {"data": "A"})
        repo_b.write("wf-2", {"data": "B"})
        state_a = repo_a.read("wf-1")
        state_b = repo_b.read("wf-2")
        assert state_a["_tenant_id"] == "T-A"
        assert state_b["_tenant_id"] == "T-B"
