"""ExecutionRouter 与 RunStore 的测试。"""

from __future__ import annotations

from pathlib import Path

from aipd_os.execution.adapter import AdapterError, ToolAdapter
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore, canonical_hash
from aipd_os.tool_adapters.builtin import build_registry
from aipd_os.tool_adapters.document_adapter import DocumentGenAdapter


def _router(tmp_path, registry=None):
    store = RunStore(str(tmp_path / "exec.db"))
    reg = registry or build_registry()
    return store, ExecutionRouter(store, reg)


def test_success_records_all_fields_and_persists(tmp_path):
    store, router = _router(tmp_path)
    out = router.run(
        "W1", "doc.generate", {"title": "T", "sections": [{"heading": "H", "body": "b"}]}
    )
    rec = out["record"]
    assert rec.status == "succeeded"
    assert rec.run_id and rec.work_id == "W1"
    assert rec.tool == "doc.generate"
    assert rec.provider and rec.version
    assert len(rec.input_hash) == 64
    assert len(rec.output_hash) == 64
    assert rec.start_time and rec.end_time
    assert rec.duration_ms >= 0
    assert isinstance(rec.cost, float)
    assert isinstance(rec.tokens_in, int)
    assert isinstance(rec.tokens_out, int)
    assert rec.error_classification == ""
    assert rec.retry_lineage == []
    assert rec.evidence_references
    assert rec.artifacts
    assert "markdown" in out["result"]

    # 持久化校验
    from_db = store.get_run(rec.run_id)
    assert from_db.status == "succeeded"
    assert from_db.input_hash == rec.input_hash
    assert from_db.output_hash == rec.output_hash
    assert len(store.list_runs(work_id="W1")) == 1


class FlakyAdapter(ToolAdapter):
    def capability_id(self) -> str:
        return "test.flaky"

    def discover(self):
        return {"id": self.capability_id(), "name": "flaky", "provider": "p",
                "version": "1", "maturity_ceiling": None, "available": True}

    def execute(self, input):
        raise AdapterError("boom", classification="transient")

    def retry_limits(self) -> int:
        return 2

    def fallback_chain(self):
        return []


def test_failing_adapter_records_retry_lineage(tmp_path):
    reg = AdapterRegistry()
    reg.register(FlakyAdapter())
    store, router = _router(tmp_path, reg)
    out = router.run("W2", "test.flaky", {})
    rec = out["record"]
    assert rec.status == "failed"
    assert len(rec.retry_lineage) >= 1
    assert rec.error_classification in ("transient", "tool_error")
    assert rec.error_message == "boom"


class PrimaryFailsAdapter(ToolAdapter):
    def capability_id(self) -> str:
        return "test.primary"

    def discover(self):
        return {"id": self.capability_id(), "name": "primary", "provider": "p",
                "version": "1", "maturity_ceiling": None, "available": True}

    def execute(self, input):
        raise AdapterError("nope", classification="tool_error")

    def retry_limits(self) -> int:
        return 1

    def fallback_chain(self):
        return ["doc.generate"]


def test_fallback_switch_records_tool_change(tmp_path):
    reg = AdapterRegistry()
    reg.register(PrimaryFailsAdapter())
    reg.register(DocumentGenAdapter())
    store, router = _router(tmp_path, reg)
    out = router.run("W3", "test.primary", {"title": "T", "sections": []})
    rec = out["record"]
    assert rec.status == "fallback"
    assert rec.tool == "doc.generate"
    assert rec.provider == "local"
    assert rec.retry_lineage  # 包含主适配器的 run_id


def test_hashes_stable_and_sensitive_to_input(tmp_path):
    store, router = _router(tmp_path)
    a = router.run("W1", "doc.generate", {"title": "A", "sections": []})
    b = router.run("W1", "doc.generate", {"title": "A", "sections": []})
    c = router.run("W1", "doc.generate", {"title": "B", "sections": []})
    assert a["record"].input_hash == b["record"].input_hash
    assert a["record"].input_hash != c["record"].input_hash
    assert a["record"].output_hash == b["record"].output_hash
    # canonical_hash 稳定性
    assert canonical_hash({"a": 1, "b": [1, 2]}) == canonical_hash({"b": [1, 2], "a": 1})
