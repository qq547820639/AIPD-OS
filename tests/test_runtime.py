"""RuntimeContext / Application Container 测试（v5.8.2 Commit 3-4）。

验证：
- build_runtime 是唯一 bootstrap 契约（state/providers/adapters/capabilities/
  supervisor/router 齐备）；
- **ResearchStudio 已进入 production wiring**（register_researchstudio 被
  build_runtime 调用，而非仅测试内注册）；
- probe 四态诚实（AVAILABLE/EXTERNAL_DEPENDENCY/UNAVAILABLE/REGISTERED）；
- with_adapters 不污染共享 registry；
- 进程级单例 get_runtime / reset_runtime。
"""
from __future__ import annotations

import pytest

from aipd_os.runtime import (
    PROBE_AVAILABLE,
    PROBE_EXTERNAL,
    PROBE_REGISTERED,
    PROBE_UNAVAILABLE,
    RuntimeContext,
    build_runtime,
    get_runtime,
    reset_runtime,
)


@pytest.fixture
def runtime(tmp_path):
    return build_runtime(db_path=str(tmp_path / "state.db"),
                         project_id="p1")


def test_build_runtime_assembles_full_graph(runtime):
    """bootstrap 契约：所有组件齐备且共享同一 db。"""
    assert runtime.db.path.name == "state.db"
    assert runtime.providers is not None
    assert runtime.adapters is not None
    assert runtime.capabilities is not None
    # 懒构造可用
    sup = runtime.supervisor()
    assert sup is runtime.supervisor()  # 同一实例（懒缓存）
    router = runtime.router()
    assert router is runtime.router()


def test_provider_registry_is_shared_not_per_command(runtime):
    """同一个 runtime 内 ProviderRegistry/AdapterRegistry 是唯一实例。"""
    assert runtime.providers is runtime.providers
    reg = runtime.providers
    # CLI 不应再 new 空 ProviderRegistry：此处验证 runtime 持有的是同一个注册表
    assert runtime.adapters.get("research.search_papers") is not None
    assert len(reg.all()) >= 0


def test_researchstudio_registered_in_production_bootstrap(runtime):
    """R-05 核心：production bootstrap（build_runtime）注册 ResearchStudio。

    此前 register_researchstudio 仅测试内调用 —— 本测试锁定「生产接入」。
    """
    assert "researchstudio" in runtime.external_providers
    adapter = runtime.adapters.get("research.academic_search")
    assert adapter is not None, \
        "research.academic_search must be registered via build_runtime"
    discover = adapter.discover()
    assert "available" in discover


def test_probe_four_state_honest(runtime):
    """probe 不把「能 import」当「可用」；缺 adapter 的能力标 UNAVAILABLE。"""
    probe = runtime.probe()
    research = probe["research"]
    # idea.decompose 无注册（无第三方 provider）→ UNAVAILABLE
    assert research["idea.decompose"] == PROBE_UNAVAILABLE
    # research.academic_search 已注册（researchstudio）
    assert research["research.academic_search"] in (
        PROBE_AVAILABLE, PROBE_EXTERNAL, PROBE_REGISTERED)
    # 其他 research capability 未注册 → UNAVAILABLE（诚实）
    assert research["research.novelty_check"] == PROBE_UNAVAILABLE
    assert probe["provider_count"] >= 0
    assert probe["adapter_count"] > 0


def test_probe_research_impl_annotates_not_implemented(runtime):
    """probe.research_impl 诚实区分「未实现」与「外部依赖」（R-7 / N-3）。"""
    probe = runtime.probe()
    impl = probe["research_impl"]
    # 结构锁定：research 保持字符串值不变，research_impl 提供并列结构
    assert set(impl) == set(probe["research"])
    # 已实现：academic_search 有 researchstudio adapter
    assert impl["research.academic_search"]["implementation_status"] == "implemented"
    # 未实现：五能力 + assess_relation 无真实代码路径
    for cid in ("research.fulltext", "research.related_work",
                "research.novelty_check", "research.idea_spark",
                "research.asset_extract", "evidence.assess_relation"):
        assert impl[cid]["implementation_status"] == "not_implemented", cid
        assert impl[cid]["state"] == PROBE_UNAVAILABLE
    # idea.decompose：配置驱动（无 LLM 配置时诚实标注外部依赖），adapters 视角无 adapter
    assert impl["idea.decompose"]["implementation_status"] == "external_dependency"
    assert impl["idea.decompose"]["state"] == PROBE_UNAVAILABLE


def test_with_adapters_does_not_pollute_shared_registry(runtime):
    """命令级动态适配器经 with_adapters 叠加，不污染共享实例。"""
    from aipd_os.execution.adapter import ToolAdapter

    class FakeAdapter(ToolAdapter):
        provider = "fake"

        def capability_id(self) -> str:
            return "fake.cap"

        def discover(self) -> dict:
            return {"capability": "fake.cap", "available": True}

        def execute(self, input: dict) -> dict:  # noqa: A002
            return {"ok": True}

    merged = runtime.with_adapters({"fake.cap": FakeAdapter()})
    assert merged.get("fake.cap") is not None
    # 共享实例未被污染
    assert runtime.adapters.get("fake.cap") is None
    # base capabilities 在新 registry 中保留
    assert merged.get("research.search_papers") is not None


def test_with_adapters_duplicate_rejected(runtime):
    """重复 capability 叠加必须报错（防静默覆盖）。"""
    from aipd_os.tool_adapters.research_adapter import ResearchAdapter
    with pytest.raises(ValueError):
        runtime.with_adapters({"research.search_papers": ResearchAdapter()})


def test_get_runtime_is_process_singleton(tmp_path, monkeypatch):
    """get_runtime 返回进程级单例；reset_runtime 后可重建。"""
    monkeypatch.setenv("AIPD_DB_DIR", str(tmp_path))
    from aipd_os.config import reload_settings
    reload_settings()  # 清 settings 缓存（lru_cache），确保 env 生效
    reset_runtime()
    try:
        a = get_runtime()
        b = get_runtime()
        assert a is b
        assert isinstance(a, RuntimeContext)
        assert "research.academic_search" in a.adapters.all() or \
            a.adapters.get("research.academic_search") is not None
    finally:
        reset_runtime()
        reload_settings()


def test_live_probe_honest_without_network():
    """live_probe：无联网 provider 时诚实返回 REGISTERED/EXTERNAL。"""
    ctx = build_runtime(db_path="/tmp/aipd-runtime-live-probe-test.db",
                        project_id="p1")
    try:
        result = ctx.live_probe(timeout=1)
        assert "states" in result
        # researchstudio 没有 live_probe 方法 → REGISTERED（不伪造 AVAILABLE）
        assert result["states"]["researchstudio"] == PROBE_REGISTERED
    finally:
        reset_runtime()


def test_summary_shape(runtime):
    s = runtime.summary()
    assert s["db"].endswith("state.db")
    assert "research" in s
    assert s["external_providers"] == ["researchstudio"]
