"""Provider SDK 核心实现。

定义正式的 Provider 抽象与能力声明 schema：

- :class:`ProbeResult`：运行时探测结果（可用 / 不可用 + 原因）；
- :func:`available` / :func:`unavailable`：构造探测结果的便捷工厂；
- :class:`Provider`：第三方 Provider 需实现的基类；
- :class:`ProviderRegistry`：注册 / 发现 / 能力声明查询；
- :func:`capability_schema`：用 jsonschema 校验能力声明结构。

不引入任何新的第三方依赖（仅使用标准库与项目已有的 ``jsonschema``）。
"""
from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional, Sequence

from jsonschema import Draft7Validator, ValidationError

# 能力声明的 JSON Schema（id / name / domain / category / evidence 等字段）
CAPABILITY_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://aipd-os.dev/schemas/capability.schema.json",
    "title": "Provider 能力声明",
    "type": "object",
    "additionalProperties": True,
    "required": ["id", "name", "domain", "category", "evidence"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "domain": {
            "type": "string",
            "description": "能力所属领域（model / image / vision / cad / research / mail / generic 等）",
        },
        "category": {
            "type": "string",
            "description": "能力类别（generation / retrieval / analysis / execution / verification 等）",
        },
        "maturity_ceiling": {
            "type": "string",
            "enum": ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"],
            "description": "真实成熟度上限，未证实为 C0 或留空",
        },
        "evidence": {
            "type": "object",
            "properties": {
                "entry_point": {"type": "string"},
                "impl_file": {"type": "string", "minLength": 1},
                "call_path": {"type": "string"},
                "test_type": {"type": "string"},
                "artifact": {"type": "string"},
                "provider_version": {"type": "string"},
                "input_hash": {"type": "string"},
                "output_hash": {"type": "string"},
                "limitations": {"type": "string"},
            },
            "required": ["impl_file"],
            "additionalProperties": True,
        },
    },
}

# 保留命名，便于外部以 ``capability_schema`` 引用
capability_schema = CAPABILITY_SCHEMA


def validate_capabilities(capabilities: Sequence[Dict[str, Any]]) -> List[str]:
    """校验一组能力声明，返回错误消息列表（为空表示全部通过）。

    :raises ValidationError: 当传入的不是可迭代对象时
    """
    validator = Draft7Validator(CAPABILITY_SCHEMA)
    errors: List[str] = []
    if not capabilities:
        return errors
    for idx, cap in enumerate(capabilities):
        errs: List[Any] = []
        for err in validator.iter_errors(cap):
            errs.append(err)
        if errs:
            errors.append(f"capability[{idx}] {cap.get('id', '<no-id>')}: "
                          f"{'; '.join(_fmt_err(e) for e in errs)}")
    return errors


def _fmt_err(err: ValidationError) -> str:
    path = "/".join(str(p) for p in err.absolute_path) or "<root>"
    return f"{path}: {err.message}"


class ProbeResult:
    """运行时探测结果。

    ``ok=True`` 表示可用；``ok=False`` 时为不可用，``reason`` 说明原因。
    """

    def __init__(self, ok: bool, reason: str = "") -> None:
        self.ok = bool(ok)
        self.reason = reason

    @property
    def available(self) -> bool:
        return self.ok

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "available": self.ok, "reason": self.reason}

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ProbeResult(ok={self.ok}, reason={self.reason!r})"


def available() -> ProbeResult:
    """构造“可用”的探测结果。"""
    return ProbeResult(ok=True, reason="")


def unavailable(reason: str) -> ProbeResult:
    """构造“不可用”的探测结果并附原因。"""
    return ProbeResult(ok=False, reason=reason)


class Provider(abc.ABC):
    """Provider 基类。

    子类需实现：

    - :attr:`name`：Provider 唯一名称；
    - :meth:`capabilities`：返回能力声明列表（必须通过 capability_schema 校验）；
    - :meth:`probe`：返回 :class:`ProbeResult`（可用 / 不可用 + 原因）；
    - :meth:`run`：执行一次调用，返回结果字典。

    :meth:`configure` 可选：在注册/运行前注入配置。
    """

    #: Provider 唯一名称（子类必须覆盖）
    name: str = "unnamed"

    @abc.abstractmethod
    def capabilities(self) -> List[Dict[str, Any]]:
        """返回本 Provider 提供的能力声明列表。"""

    def configure(self, config: Dict[str, Any]) -> None:
        """注入配置（可选）。默认实现为无操作。"""

    @abc.abstractmethod
    def probe(self) -> ProbeResult:
        """运行时探测：返回可用 / 不可用 + 原因。"""

    @abc.abstractmethod
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行一次调用，返回结果字典。"""

    def validate_capabilities(self) -> List[str]:
        """校验自身能力声明，返回错误列表（为空表示通过）。"""
        return validate_capabilities(self.capabilities())


class ProviderRegistry:
    """按 Provider 名称与能力 id 注册 / 发现 / 查询。"""

    def __init__(self) -> None:
        self._providers: Dict[str, Provider] = {}
        self._by_capability: Dict[str, str] = {}

    def register(self, provider: Provider) -> None:
        """注册一个 Provider；名称重复或能力 id 冲突时报错。"""
        if not isinstance(provider, Provider):
            raise TypeError(f"expected a Provider, got {type(provider).__name__}")
        if provider.name in self._providers:
            raise ValueError(f"provider already registered: {provider.name}")
        errors = provider.validate_capabilities()
        if errors:
            raise ValueError(f"provider {provider.name} declares invalid capabilities: {errors}")
        for cap in provider.capabilities():
            cid = cap["id"]
            if cid in self._by_capability:
                raise ValueError(
                    f"capability {cid!r} already claimed by provider "
                    f"{self._by_capability[cid]!r}")
        self._providers[provider.name] = provider
        for cap in provider.capabilities():
            self._by_capability[cap["id"]] = provider.name

    def get(self, name: str) -> Optional[Provider]:
        return self._providers.get(name)

    def get_by_capability(self, capability_id: str) -> Optional[Provider]:
        owner = self._by_capability.get(capability_id)
        if owner is None:
            return None
        return self._providers.get(owner)

    def all(self) -> List[Provider]:
        return list(self._providers.values())

    def names(self) -> List[str]:
        return list(self._providers.keys())

    def capability_ids(self) -> List[str]:
        return list(self._by_capability.keys())

    def discover(self) -> List[Dict[str, Any]]:
        """返回所有 Provider 的能力声明 + 探测结果（供能力矩阵/医生体检用）。"""
        out: List[Dict[str, Any]] = []
        for provider in self._providers.values():
            probe = provider.probe()
            out.append({
                "provider": provider.name,
                "available": probe.available,
                "probe_reason": probe.reason,
                "capabilities": provider.capabilities(),
            })
        return out

    def __contains__(self, name: str) -> bool:
        return name in self._providers

    def __len__(self) -> int:
        return len(self._providers)


__all__ = [
    "CAPABILITY_SCHEMA",
    "capability_schema",
    "validate_capabilities",
    "ProbeResult",
    "available",
    "unavailable",
    "Provider",
    "ProviderRegistry",
]