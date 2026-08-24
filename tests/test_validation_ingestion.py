"""EVT/DVT/PVT Ingestion 测试（v5.10 Milestone 3）。

覆盖：
- CSV import
- JSON import
- Malformed input
- Missing columns
- Unknown stage
- FAIL creates issue
- Duplicate import / idempotency
- Multi-tenant isolation
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.validation.ingestion import IngestionService
from aipd_os.validation.issues import IssueService
from aipd_os.validation.service import ValidationService


@pytest.fixture
def db():
    """创建临时数据库。"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        d = AIPDStateDB(str(db_path))
        d.ensure_default_tenant("t1")
        d.ensure_default_tenant("t2")
        d.init_project("t1", "p1", "Project 1", "Goal 1")
        d.init_project("t1", "p2", "Project 2", "Goal 2")
        d.init_project("t2", "p1", "Project 1 T2", "Goal 1 T2")
        yield d


@pytest.fixture
def svc(db):
    """创建 IngestionService。"""
    vs = ValidationService(db)
    is_ = IssueService(db)
    return IngestionService(vs, is_)


@pytest.fixture
def tmp_dir():
    """创建临时目录。"""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# =====================================================================
# CSV import tests
# =====================================================================

class TestCSVImport:
    """CSV 导入测试。"""

    def test_import_valid_csv(self, svc, tmp_dir):
        """导入有效 CSV。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail,notes\n"
            "Tensile Test,S001,150 MPa,pass,OK\n"
            "Impact Test,S002,25 J,fail,Below threshold\n",
            encoding="utf-8",
        )

        result = svc.ingest_file("t1", "p1", csv_file, "EVT")
        assert result.records_imported == 2
        assert result.tests_created == 2
        assert result.runs_created == 2
        assert result.results_created == 2
        assert result.issues_created == 1  # FAIL creates issue
        assert len(result.errors) == 0

    def test_import_csv_with_plan(self, svc, tmp_dir):
        """导入 CSV 到指定计划。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail,notes\n"
            "Test1,S001,100,pass,OK\n",
            encoding="utf-8",
        )

        result = svc.ingest_file("t1", "p1", csv_file, "EVT", plan_id="plan_123")
        assert result.records_imported == 1
        assert len(result.errors) == 0


# =====================================================================
# JSON import tests
# =====================================================================

class TestJSONImport:
    """JSON 导入测试。"""

    def test_import_valid_json_array(self, svc, tmp_dir):
        """导入有效 JSON 数组。"""
        json_file = tmp_dir / "test.json"
        json_file.write_text(json.dumps([
            {"test_item": "Tensile", "sample_id": "S001", "result": "150", "pass_fail": "pass"},
            {"test_item": "Impact", "sample_id": "S002", "result": "25", "pass_fail": "fail"},
        ]), encoding="utf-8")

        result = svc.ingest_file("t1", "p1", json_file, "DVT")
        assert result.records_imported == 2
        assert result.issues_created == 1

    def test_import_valid_json_object(self, svc, tmp_dir):
        """导入有效 JSON 对象（含 records 键）。"""
        json_file = tmp_dir / "test.json"
        json_file.write_text(json.dumps({
            "records": [
                {"test_item": "Test1", "pass_fail": "pass"},
            ]
        }), encoding="utf-8")

        result = svc.ingest_file("t1", "p1", json_file, "PVT")
        assert result.records_imported == 1


# =====================================================================
# Schema validation tests
# =====================================================================

class TestSchemaValidation:
    """Schema 验证测试。"""

    def test_missing_test_item(self, svc, tmp_dir):
        """缺少 test_item 的记录被拒绝。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "sample_id,result,pass_fail\n"
            "S001,150,pass\n",
            encoding="utf-8",
        )

        result = svc.ingest_file("t1", "p1", csv_file, "EVT")
        assert result.records_imported == 0
        assert len(result.errors) > 0

    def test_missing_pass_fail_imported_as_error(self, svc, tmp_dir):
        """缺少 pass_fail 的记录导入为 IMPORT_ERROR 状态。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail\n"
            "Test1,S001,150,\n",
            encoding="utf-8",
        )

        result = svc.ingest_file("t1", "p1", csv_file, "EVT")
        assert result.records_imported == 1
        # 空 pass_fail → warning，结果为 IMPORT_ERROR
        assert len(result.warnings) > 0

    def test_unknown_stage(self, svc, tmp_dir):
        """无效阶段被拒绝。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,pass_fail\n"
            "Test1,pass\n",
            encoding="utf-8",
        )

        result = svc.ingest_file("t1", "p1", csv_file, "INVALID")
        assert result.records_imported == 0
        assert len(result.errors) > 0

    def test_empty_file(self, svc, tmp_dir):
        """空文件返回警告。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text("test_item,pass_fail\n", encoding="utf-8")

        result = svc.ingest_file("t1", "p1", csv_file, "EVT")
        assert result.records_imported == 0
        assert len(result.warnings) > 0

    def test_unsupported_format(self, svc, tmp_dir):
        """不支持的文件格式被拒绝。"""
        bad_file = tmp_dir / "test.xyz"
        bad_file.write_text("data", encoding="utf-8")

        result = svc.ingest_file("t1", "p1", bad_file, "EVT")
        assert result.records_imported == 0
        assert len(result.errors) > 0


# =====================================================================
# Issue creation tests
# =====================================================================

class TestIssueCreation:
    """Issue 创建测试。"""

    def test_fail_creates_issue(self, svc, tmp_dir):
        """失败记录自动创建 Issue。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail,notes\n"
            "Test1,S001,50,fail,Below min\n",
            encoding="utf-8",
        )

        result = svc.ingest_file("t1", "p1", csv_file, "EVT")
        assert result.issues_created == 1

        # Verify issue exists
        issues = svc._issues.list_issues("t1", "p1")
        assert len(issues) == 1
        assert "Test1" in issues[0].title

    def test_pass_does_not_create_issue(self, svc, tmp_dir):
        """通过记录不创建 Issue。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail\n"
            "Test1,S001,150,pass\n",
            encoding="utf-8",
        )

        result = svc.ingest_file("t1", "p1", csv_file, "EVT")
        assert result.issues_created == 0


# =====================================================================
# Idempotency tests
# =====================================================================

class TestIdempotency:
    """幂等性测试。"""

    def test_same_data_different_imports(self, svc, tmp_dir):
        """相同数据多次导入不会创建重复测试（按名称匹配）。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail\n"
            "Test1,S001,150,pass\n",
            encoding="utf-8",
        )

        result1 = svc.ingest_file("t1", "p1", csv_file, "EVT")
        result2 = svc.ingest_file("t1", "p1", csv_file, "EVT")

        # 第二次导入不应创建新测试（按名称匹配）
        assert result1.tests_created == 1
        assert result2.tests_created == 0  # 复用已有测试


# =====================================================================
# Multi-tenant isolation tests
# =====================================================================

class TestMultiTenantIsolation:
    """多租户隔离测试。"""

    def test_different_tenants_isolated(self, svc, tmp_dir):
        """不同租户的导入互相隔离。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail\n"
            "Test1,S001,150,pass\n",
            encoding="utf-8",
        )

        svc.ingest_file("t1", "p1", csv_file, "EVT")
        svc.ingest_file("t2", "p1", csv_file, "EVT")

        # 各自独立
        t1_tests = svc._validation.list_tests("t1", "p1")
        t2_tests = svc._validation.list_tests("t2", "p1")
        assert len(t1_tests) == 1
        assert len(t2_tests) == 1

    def test_different_projects_isolated(self, svc, tmp_dir):
        """不同项目的导入互相隔离。"""
        csv_file = tmp_dir / "test.csv"
        csv_file.write_text(
            "test_item,sample_id,result,pass_fail\n"
            "Test1,S001,150,pass\n",
            encoding="utf-8",
        )

        svc.ingest_file("t1", "p1", csv_file, "EVT")
        svc.ingest_file("t1", "p2", csv_file, "EVT")

        p1_tests = svc._validation.list_tests("t1", "p1")
        p2_tests = svc._validation.list_tests("t1", "p2")
        assert len(p1_tests) == 1
        assert len(p2_tests) == 1


# =====================================================================
# Multi-file import tests
# =====================================================================

class TestMultiFileImport:
    """多文件导入测试。"""

    def test_import_multiple_files(self, svc, tmp_dir):
        """导入多个文件。"""
        csv1 = tmp_dir / "test1.csv"
        csv1.write_text(
            "test_item,sample_id,result,pass_fail\n"
            "Test1,S001,150,pass\n",
            encoding="utf-8",
        )
        csv2 = tmp_dir / "test2.csv"
        csv2.write_text(
            "test_item,sample_id,result,pass_fail\n"
            "Test2,S002,25,fail\n",
            encoding="utf-8",
        )

        result = svc.ingest_files("t1", "p1", [csv1, csv2], "EVT")
        assert result.records_imported == 2
        assert result.issues_created == 1
