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
    assert rec.project_id == ""
    assert rec.adapter_id == "doc.generate"
    assert rec.capability == "doc.generate"
    assert rec.retry_parent == ""
    assert rec.started_at == rec.start_time
    assert rec.completed_at == rec.end_time
    assert rec.evidence_references
    assert rec.artifacts
    assert "markdown" in out["result"]

    # 持久化校验
    from_db = store.get_run(rec.run_id)
    assert from_db.status == "succeeded"
    assert from_db.input_hash == rec.input_hash
    assert from_db.output_hash == rec.output_hash
    assert from_db.project_id == rec.project_id
    assert from_db.adapter_id == rec.adapter_id
    assert from_db.capability == rec.capability
    assert from_db.retry_parent == rec.retry_parent
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
    assert rec.retry_parent == rec.retry_lineage[-1]
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


def test_project_id_passes_through_context(tmp_path):
    store, router = _router(tmp_path)
    out = router.run(
        "W1", "doc.generate", {"title": "T", "sections": []},
        context={"project_id": "PRJ1"},
    )
    rec = out["record"]
    assert rec.status == "succeeded"
    assert rec.project_id == "PRJ1"
    assert rec.adapter_id == "doc.generate"
    assert rec.capability == "doc.generate"
    rec2 = store.get_run(rec.run_id)
    assert rec2.project_id == "PRJ1"
    assert rec2.adapter_id == "doc.generate"
    assert rec2.capability == "doc.generate"

UNIFIED_KEYS = {
    "run_id", "project_id", "work_id", "adapter_id", "provider",
    "provider_version", "capability", "input_hash", "output_hash",
    "started_at", "completed_at", "status", "cost", "token_usage",
    "retry_parent", "fallback_from", "error_type", "evidence_ids",
    "artifact_ids",
}


def test_unified_record_all_19_keys_and_fallback_round_trip(tmp_path):
    reg = AdapterRegistry()
    reg.register(PrimaryFailsAdapter())
    reg.register(DocumentGenAdapter())
    store, router = _router(tmp_path, reg)
    out = router.run(
        "WF", "test.primary", {"title": "T", "sections": []},
        context={"project_id": "PRJ_F"},
    )
    rec = out["record"]
    assert rec.status == "fallback"
    assert rec.fallback_from == "test.primary"  # 从主能力降级而来
    assert rec.retry_lineage  # 主尝试的 run_id 已进入 lineage

    ur = rec.unified_record()
    assert set(ur.keys()) == UNIFIED_KEYS
    assert ur["project_id"] == "PRJ_F"
    assert ur["work_id"] == "WF"
    assert ur["adapter_id"] == "doc.generate"
    assert ur["capability"] == "doc.generate"
    assert ur["fallback_from"] == "test.primary"
    assert ur["provider_version"] == rec.version
    assert ur["started_at"] == rec.start_time
    assert ur["completed_at"] == rec.end_time
    assert ur["token_usage"] == {"input": rec.tokens_in, "output": rec.tokens_out}
    assert ur["error_type"] == rec.error_classification
    assert ur["evidence_ids"] == rec.evidence_references
    assert ur["artifact_ids"] == rec.artifacts
    assert ur["retry_parent"] == rec.retry_parent

    # round-trip through RunStore
    from_db = store.get_run(rec.run_id)
    assert from_db.project_id == "PRJ_F"
    assert from_db.capability == "doc.generate"
    assert from_db.retry_parent == rec.retry_parent
    assert from_db.fallback_from == "test.primary"
    assert from_db.unified_record()["token_usage"] == {
        "input": from_db.tokens_in, "output": from_db.tokens_out,
    }
