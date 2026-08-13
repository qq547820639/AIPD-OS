"""Runtime Context / Application Container（v5.8.2 Commit 3）。

**问题**：CLI 各 command 内曾各自 ``ProviderRegistry()`` / ``AdapterRegistry()``
重新装配空实例（如旧 ``_find_idea_decompose_provider``），导致「注册过但
runtime 发现不了」的假象。本模块建立唯一 bootstrap 契约：

:func:`build_runtime` —— 唯一装配入口：
1. load settings（env > 配置文件 > 默认）
2. initialize State（AIPDStateDB，migration runner 全链）
3. initialize ProviderRegistry（通用 Provider：idea.decompose 等第三方）
4. register external providers（ResearchStudio 等，Commit 4 接入）
5. initialize AdapterRegistry（builtin + researchstudio adapter）
6. initialize ExecutionRouter（懒构造，RunStore 与 state db 同目录）
7. initialize Supervisor（懒构造，同 db 文件 + state_db 共享）
8. probe capabilities（本地确定性探测；联网探测独立方法）
9. return :class:`RuntimeContext`

:func:`get_runtime` —— 进程级单例（所有 transport 共用同一 runtime 装配，
不重复 new registry）。CLI / Web / MCP / Supervisor 统一依赖本契约。

原则：CLI 不能自己 new 一套 ProviderRegistry；Web 不能自己 new 第二套；
MCP 不能使用另一套。状态存储（StateService）与执行装配（RuntimeContext）
是两个正交层次，Web/MCP 薄层只依赖 StateService（见 state/server.py），
执行层统一经本模块。

Honesty：probe 只报告真实注册/探测结果，不把「能 import」当作「可用」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aipd_os.config import Settings, get_settings
from aipd_os.state.db import AIPDStateDB

# ---------------------------------------------------------------------------
# 可用性四态（R-30；不把能 import 当可用）
# ---------------------------------------------------------------------------
PROBE_AVAILABLE = "AVAILABLE"  # 真实可用（adapter 注册 + discover.available）
PROBE_UNAVAILABLE = "UNAVAILABLE"  # 未注册 / 不可用
PROBE_EXTERNAL = "EXTERNAL_DEPENDENCY"  # 已注册但依赖外部服务未配置
PROBE_PARTIAL = "PARTIAL"  # 多源部分可用（failed_sources 非空）
PROBE_REGISTERED = "REGISTERED"  # 已注册，实时可用性需 live probe


@dataclass
class RuntimeContext:
    """一次进程运行的唯一装配产物（所有 transport 共享）。"""

    settings: Settings
    db: AIPDStateDB
    providers: Any  # ProviderRegistry（providers.sdk）
    adapters: Any  # AdapterRegistry（execution.registry）
    capabilities: Any  # CapabilityRegistry（registry.load_default_registry）
    tenant_id: str = "default"
    project_id: str | None = None
    # 外部 provider 实例（researchstudio 等），供 live probe / 显式持有
    external_providers: dict[str, Any] = field(default_factory=dict)
    _supervisor: Any = field(default=None, init=False, repr=False)
    _router: Any = field(default=None, init=False, repr=False)
    _run_store: Any = field(default=None, init=False, repr=False)

    # ----------------------------------------------------------- lazy parts
    def supervisor(self) -> Any:
        """懒构造 Supervisor（同 db 文件，共享 state_db）。"""
        if self._supervisor is None:
            from aipd_os.supervisor import Supervisor
            self._supervisor = Supervisor(
                str(self.db.path), tenant_id=self.tenant_id,
                project_id=self.project_id, state_db=self.db)
        return self._supervisor

    def router(self) -> Any:
        """懒构造 ExecutionRouter（RunStore 与 state db 同目录）。"""
        if self._router is None:
            from aipd_os.execution.execution_router import ExecutionRouter
            from aipd_os.execution.runs import RunStore
            if self._run_store is None:
                self._run_store = RunStore(
                    str(self.db.path.parent / "execution_runs.db"))
            self._router = ExecutionRouter(self._run_store, self.adapters)
        return self._router

    def with_adapters(self, extra: dict[str, Any]) -> Any:
        """返回 base adapters + extra 的新 registry（不污染共享实例）。

        命令级动态适配器（如 idea.structure 依赖 decomposer 实例）不能注册进
        共享 registry（重复注册会 ValueError），因此复制 base 再叠加。
        """
        from aipd_os.execution.registry import AdapterRegistry
        merged = AdapterRegistry()
        for adapter in self.adapters.all():
            merged.register(adapter)
        for capability_id, adapter in extra.items():
            existing = merged.get(capability_id)
            if existing is not None:
                raise ValueError(
                    f"runtime.with_adapters: capability already registered: "
                    f"{capability_id}")
            merged.register(adapter)
        return merged

    # ---------------------------------------------------------------- probe
    def probe(self) -> dict[str, Any]:
        """本地确定性探测（不联网）：registry 状态 + 四态归类。"""
        providers = [p.name for p in self.providers.all()]
        adapter_caps = sorted(a.capability_id() for a in self.adapters.all())
        research: dict[str, Any] = {}
        for cid in ("research.academic_search", "research.fulltext",
                    "research.related_work", "research.novelty_check",
                    "research.idea_spark", "research.asset_extract",
                    "evidence.assess_relation", "idea.decompose"):
            adapter = self.adapters.get(cid)
            if adapter is None:
                research[cid] = PROBE_UNAVAILABLE
                continue
            try:
                available = adapter.discover().get("available", True)
            except Exception:  # noqa: BLE001 - probe 不抛（诚实标注）
                research[cid] = PROBE_EXTERNAL
                continue
            research[cid] = PROBE_AVAILABLE if available else PROBE_EXTERNAL
        # v5.9.1：product.* 动态四态（P0-38/64）—— adapter 已装但 provider
        # 未配置 → EXTERNAL_DEPENDENCY（声明存在 ≠ 可用）
        product: dict[str, Any] = {}
        for cid in ("product.derive_insights", "product.identify_opportunity",
                    "product.derive_principles", "product.derive_requirements",
                    "product.derive_features", "product.create_snapshot",
                    "product.definition_gate"):
            adapter = self.adapters.get(cid)
            if adapter is None:
                product[cid] = PROBE_UNAVAILABLE
                continue
            try:
                available = adapter.discover().get("available", True)
            except Exception:  # noqa: BLE001
                product[cid] = PROBE_EXTERNAL
                continue
            product[cid] = PROBE_AVAILABLE if available else PROBE_EXTERNAL
        return {
            "providers": providers,
            "provider_count": len(providers),
            "adapter_capabilities": adapter_caps,
            "adapter_count": len(adapter_caps),
            "research": research,
            "product": product,
            "external_providers": sorted(self.external_providers),
        }

    def live_probe(self, timeout: int = 15) -> dict[str, Any]:
        """联网探测外部 provider（可失败；不伪造成功）。

        仅对显式注册的 live-probe-capable provider 执行；结果含
        ``available_sources`` / ``failed_sources`` / 四态归类。
        """
        out: dict[str, Any] = {
            "available_sources": [],
            "failed_sources": [],
            "states": {},
        }
        for name, provider in self.external_providers.items():
            prober = getattr(provider, "live_probe", None)
            if prober is None:
                out["states"][name] = PROBE_REGISTERED
                continue
            try:
                result = prober(timeout=timeout)  # type: ignore[operator]
            except Exception as exc:  # noqa: BLE001 - 联网失败诚实记录
                out["failed_sources"].append({"provider": name, "error": str(exc)})
                out["states"][name] = PROBE_EXTERNAL
                continue
            ok = result.get("available_sources", [])
            failed = result.get("failed_sources", [])
            out["available_sources"].extend(
                {"provider": name, "source": s} for s in ok)
            out["failed_sources"].extend(
                {"provider": name, "source": s, "error": e}
                for s, e in failed)
            if ok and failed:
                out["states"][name] = PROBE_PARTIAL
            elif ok:
                out["states"][name] = PROBE_AVAILABLE
            else:
                out["states"][name] = PROBE_EXTERNAL
        return out

    # -------------------------------------------------------------- helpers
    def summary(self) -> dict[str, Any]:
        """human-readable runtime summary（owner UX / CLI）。"""
        probe = self.probe()
        return {
            "db": str(self.db.path),
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "providers": probe["provider_count"],
            "adapters": probe["adapter_count"],
            "research": probe["research"],
            "external_providers": probe["external_providers"],
        }


def _resolve_db_path(settings: Settings, db_path: str | None) -> Path:
    if db_path:
        return Path(db_path)
    return Path(settings.db_dir) / "state.db"


def build_runtime(settings: Settings | None = None,
                  db_path: str | None = None,
                  encryption_key: str | None = None,
                  tenant_id: str = "default",
                  project_id: str | None = None,
                  register_external: bool = True,
                  make_default: bool = False) -> RuntimeContext:
    """唯一 runtime 装配入口（bootstrap contract）。

    1. settings（env > 配置文件 > 默认）
    2. State（AIPDStateDB，migration runner 全链）
    3. ProviderRegistry
    4. 外部 provider 注册（register_external=True 时：ResearchStudio）
    5. AdapterRegistry（builtin + researchstudio adapter）
    6-7. ExecutionRouter / Supervisor（懒构造）
    8. probe 由调用方按需执行（:meth:`RuntimeContext.probe`）

    v5.9.2（§18/52）：``make_default=True`` 时安装为进程级默认
    （等价 :func:`install_runtime`）—— CLI/Web/MCP 各自显式注入自己的
    runtime；只有需要进程级默认语义的 transport 才 make_default。
    """
    settings = settings or get_settings()
    key = encryption_key if encryption_key is not None \
        else settings.data_encryption_key
    db = AIPDStateDB(str(_resolve_db_path(settings, db_path)),
                     encryption_key=key)

    from aipd_os.providers.sdk import ProviderRegistry
    from aipd_os.registry import load_default_registry
    from aipd_os.tool_adapters.builtin import build_registry

    providers = ProviderRegistry()
    adapters = build_registry()
    capabilities = load_default_registry()

    ctx = RuntimeContext(
        settings=settings, db=db, providers=providers, adapters=adapters,
        capabilities=capabilities, tenant_id=tenant_id, project_id=project_id)

    if register_external:
        _register_external_providers(ctx)

    if make_default:
        install_runtime(ctx)

    return ctx


def install_runtime(runtime: RuntimeContext) -> None:
    """显式安装进程级默认 runtime（§18/52 语义清晰化）。

    get_runtime() 返回已安装实例；未安装时懒构建（build_runtime 默认
    make_default=False —— 同一次 request 不会因为两次 build 出现两套
    registry 的意外）。
    """
    global _runtime
    _runtime = runtime


def _register_external_providers(ctx: RuntimeContext) -> None:
    """注册外部 provider 进 runtime（v5.8.2 Commit 4：ResearchStudio production wiring）。

    配置驱动 LLM Provider 装配（v5.9.2 N-1）：
    - 当 ``AIPD_MODEL_API_KEY`` 与 ``AIPD_MODEL_BASE_URL`` 均非空时，构造通用
      :class:`LlmClient` 并装配 ``LlmProductIntelligenceProvider``（product.*
      adapters 获得真实 provider）与 ``LlmIdeaDecompositionProvider``
      （经 ``IdeaDecompositionProviderAdapter`` 注册进 ProviderRegistry 的
      ``idea.decompose`` capability）；
    - 未配置时保持诚实降级：product.* 以 ``provider=None`` 注册（discover
      available=False → probe EXTERNAL_DEPENDENCY），idea.decompose 不注册
      （probe UNAVAILABLE），与基线行为完全一致，绝不注册 fake。

    原则：注册 ≠ 可用。注册进 AdapterRegistry 后由 probe 判定四态；
    测试内注册成功不代表 production 已接入 —— 本函数即 production 接入点。
    """
    from aipd_os.research.providers.researchstudio import register_researchstudio
    from aipd_os.tool_adapters.product_adapters import register_product_adapters

    provider = register_researchstudio(ctx.adapters)
    ctx.external_providers["researchstudio"] = provider

    api_key = ctx.settings.model_api_key
    base_url = ctx.settings.model_base_url
    model_name = ctx.settings.model_name
    if api_key and base_url:
        from aipd_os.idea.decomposer import IdeaDecompositionProviderAdapter
        from aipd_os.llm.client import LlmClient
        from aipd_os.llm.idea_decomposer_provider import (
            LlmIdeaDecompositionProvider,
        )
        from aipd_os.llm.product_intelligence_provider import (
            LlmProductIntelligenceProvider,
        )

        client = LlmClient(
            endpoint=base_url, api_key=api_key,
            model=model_name or "gpt-4o-mini")

        pi_provider = LlmProductIntelligenceProvider(client)
        register_product_adapters(ctx.adapters, ctx.db, provider=pi_provider)
        ctx.external_providers["llm-product-intelligence"] = pi_provider

        dec_provider = LlmIdeaDecompositionProvider(client)
        ctx.providers.register(IdeaDecompositionProviderAdapter(dec_provider))
        ctx.external_providers["llm-idea-decomposer"] = dec_provider
    else:
        # v5.9.1（P0-10/38）：product.* adapters 注册进 production bootstrap。
        # 生产 Provider 未配置 → discover.available=False → probe 诚实
        # EXTERNAL_DEPENDENCY；execute 写外部任务包（不伪造成功）。
        register_product_adapters(ctx.adapters, ctx.db, provider=None)


# ---------------------------------------------------------------------------
# 进程级单例（所有 transport 共用同一装配；测试用 reset_runtime 隔离）
# ---------------------------------------------------------------------------
_runtime: RuntimeContext | None = None


def get_runtime() -> RuntimeContext:
    """进程级 runtime 单例（懒构建；CLI/Web/MCP/Supervisor 统一入口）。"""
    global _runtime
    if _runtime is None:
        _runtime = build_runtime()
    return _runtime


def reset_runtime() -> None:
    """清除进程级单例（测试隔离 / 配置热重载）。"""
    global _runtime
    _runtime = None


__all__ = [
    "RuntimeContext",
    "build_runtime",
    "install_runtime",
    "get_runtime",
    "reset_runtime",
    "PROBE_AVAILABLE",
    "PROBE_UNAVAILABLE",
    "PROBE_EXTERNAL",
    "PROBE_PARTIAL",
    "PROBE_REGISTERED",
]
