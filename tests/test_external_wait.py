"""外部等待视图测试：确定性分组 + 中文可读输出。"""
from __future__ import annotations

from aipd_os.experience.external_wait import summarize_external_wait


def test_empty_returns_no_wait():
    out = summarize_external_wait([])
    assert out["count"] == 0
    assert out["supplier"] == [] and out["lab"] == [] and out["other"] == []
    assert "无外部等待" in out["summary"]


def test_supplier_bucket():
    wait = [{"source_type": "supplier", "source_id": "s1",
             "target_type": "quote", "target_id": "q1"},
            {"source_type": "design", "source_id": "d1",
             "target_type": "rfq", "target_id": "r1"}]
    out = summarize_external_wait(wait)
    assert len(out["supplier"]) == 2
    assert out["lab"] == [] and out["other"] == []
    assert out["count"] == 2
    # 自然语言，不暴露源/目标内部代号
    assert all(":" not in s for s in out["supplier"])


def test_lab_bucket():
    wait = [{"source_type": "lab", "source_id": "L1",
             "target_type": "test", "target_id": "t1"},
            {"source_type": "design", "source_id": "d1",
             "target_type": "evt", "target_id": "e1"}]
    out = summarize_external_wait(wait)
    assert len(out["lab"]) == 2
    assert out["supplier"] == [] and out["other"] == []


def test_note_goes_to_other():
    wait = [{"note": "project status is blocked_external"}]
    out = summarize_external_wait(wait)
    assert out["other"] == ["项目因依赖外部方而暂停推进"]
    assert out["supplier"] == [] and out["lab"] == []


def test_supplier_and_lab_mixed():
    wait = [{"source_type": "vendor", "source_id": "v1",
             "target_type": "quote", "target_id": "q1"},
            {"source_type": "lab", "source_id": "L1",
             "target_type": "sample", "target_id": "sp1"}]
    out = summarize_external_wait(wait)
    assert len(out["supplier"]) == 1
    assert len(out["lab"]) == 1
    assert out["count"] == 2
    assert "供应商" in out["summary"] and "测试实验室" in out["summary"]


def test_deterministic():
    wait = [{"source_type": "supplier", "source_id": "s1",
             "target_type": "quote", "target_id": "q1"},
            {"source_type": "lab", "source_id": "L1",
             "target_type": "test", "target_id": "t1"}]
    assert summarize_external_wait(wait) == summarize_external_wait(wait)
