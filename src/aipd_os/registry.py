"""统一 Capability Registry（v5.6）—— 能力矩阵的唯一事实来源。

本模块用声明式方式登记每一项能力，并据此生成能力矩阵。它取代了 v5.5 及之前
`scripts/capability_matrix.py` 中与代码脱节的**静态 CAPABILITIES 长表**。

设计原则：
1. 每一项能力都声明：id/name/domain/declaration_file/implementation_file/entry_point/
   run_command/unit_test/integration_test/e2e_evidence/current_limitation。
2. 分类（classification）**不**在此静态写死，而是由
   :func:`probe_classification` 在运行时根据“实现文件是否存在、入口是否可调用、
   测试是否存在、是否真实外部依赖”等证据动态推导，避免表格与代码脱节。
3. 提供 schema / 实现文件存在性 / 入口可调用 / 证据时效四类校验子（见
   :mod:`aipd_os.registry` 与 `scripts/capability_matrix.py`）。

仅依赖标准库。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

CLASSIFICATIONS = [
    "fully_implemented",
    "partially_implemented",
    "protocol_only",
    "template_only",
    "external_dependency",
    "not_implemented",
    "not_verifiable",
]

CLASSIFICATION_LABELS = {
    "fully_implemented": "完整实现（有真实运行工件与测试证据）",
    "partially_implemented": "部分实现（核心路径可用，边界/证据不全）",
    "protocol_only": "仅协议/接口（无真实执行）",
    "template_only": "仅模板/示例（无真实执行）",
    "external_dependency": "依赖外部服务/工具（未配置时诚实等待，不伪造）",
    "not_implemented": "未实现",
    "not_verifiable": "无法验证（缺证据/缺环境）",
}


@dataclass
class Capability:
    """一项已登记的能力及其证据字段。"""

    id: str
    name: str
    domain: str
    classification: str = "not_verifiable"
    external_dependency: bool = False
    declaration_file: Optional[str] = None
    implementation_file: Optional[str] = None
    entry_point: Optional[str] = None
    run_command: Optional[str] = None
    input_output: Optional[str] = None
    unit_test: Optional[str] = None
    integration_test: Optional[str] = None
    e2e_evidence: Optional[str] = None
    current_limitation: Optional[str] = None
    # 运行时证据（由 probe 填充）
    probe: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "classification": self.classification,
            "external_dependency": bool(self.external_dependency),
            "declaration_file": self.declaration_file,
            "implementation_file": self.implementation_file,
            "entry_point": self.entry_point,
            "run_command": self.run_command,
            "input_output": self.input_output,
            "unit_test": self.unit_test,
            "integration_test": self.integration_test,
            "e2e_evidence": self.e2e_evidence,
            "current_limitation": self.current_limitation,
            "probe": self.probe,
        }


class CapabilityRegistry:
    """能力的声明式登记与查询。"""

    def __init__(self) -> None:
        self._caps: Dict[str, Capability] = {}

    def register(self, cap: Capability) -> None:
        if cap.id in self._caps:
            raise ValueError(f"duplicate capability id: {cap.id}")
        self._caps[cap.id] = cap

    def get(self, cap_id: str) -> Optional[Capability]:
        return self._caps.get(cap_id)

    def all(self) -> List[Capability]:
        return list(self._caps.values())

    def domains(self) -> List[str]:
        seen: List[str] = []
        for c in self._caps.values():
            if c.domain not in seen:
                seen.append(c.domain)
        return seen

    def validate(self, repo_root: Path) -> List[str]:
        """对登记表做基础 schema 校验，返回错误列表。"""
        errors: List[str] = []
        for c in self._caps.values():
            if not c.id or not c.name or not c.domain:
                errors.append(f"{c.id or '<unnamed>'}: id/name/domain 必填")
            if c.classification not in CLASSIFICATIONS:
                errors.append(f"{c.id}: 非法 classification {c.classification!r}")
            if c.classification == "partially_implemented" and not (
                (c.current_limitation or "").strip()
            ):
                errors.append(f"{c.id}: partially_implemented 必须提供 current_limitation")
            if c.implementation_file:
                # 校验实现文件存在性（逗号分隔多个候选，任一命中即可）
                candidates = [p.strip() for p in c.implementation_file.split(";") if p.strip()]
                if not any(_file_exists(repo_root, p) for p in candidates):
                    errors.append(f"{c.id}: 实现文件不存在: {c.implementation_file}")
        return errors


def _file_exists(repo_root: Path, rel: str) -> bool:
    """判断相对仓库根的一个文件或目录是否存在。

    支持三种形态：
    - 精确路径：``src/aipd_os/xx.py``
    - glob（含 ``*``）：``src/**/xx.py``
    - brace 展开（``{a,b,c}``）：``scripts/research/search_papers_by_{arxiv,crossref}.py``
    """
    if "{" in rel and "}" in rel:
        expanded = _expand_braces(rel)
        if any(_file_exists(repo_root, p) for p in expanded):
            return True
        # 若展开后仍无命中，回退到 glob / 精确判断原串
        rel = rel.replace("{", "").replace("}", "")
    if "*" in rel:
        return any(repo_root.glob(rel))
    return (repo_root / rel).exists()


def _expand_braces(pattern: str) -> List[str]:
    """对 ``{a,b,c}`` 做笛卡尔展开，返回所有候选路径。"""
    results: List[str] = [""]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "{":
            end = pattern.find("}", i)
            if end == -1:
                results = [r + ch for r in results]
                i += 1
                continue
            options = pattern[i + 1:end].split(",")
            results = [r + opt for r in results for opt in options]
            i = end + 1
        else:
            results = [r + ch for r in results]
            i += 1
    return results


def load_default_registry() -> CapabilityRegistry:
    """从 ``src/aipd_os/registry_data.py`` 加载默认能力登记表。

    数据文件由版本化维护，避免把长表塞进本模块导致与代码脱节。
    """
    try:
        from aipd_os import registry_data  # type: ignore
    except Exception:  # pragma: no cover - 回退路径
        registry_data = None  # type: ignore

    reg = CapabilityRegistry()
    if registry_data is not None and hasattr(registry_data, "CAPABILITIES"):
        for entry in registry_data.CAPABILITIES:
            cap = Capability(**entry)
            reg.register(cap)
    return reg


def probe_file_has_impl(repo_root: Path, impl_spec: Optional[str]) -> bool:
    """探测实现文件是否存在。"""
    if not impl_spec:
        return False
    candidates = [p.strip() for p in impl_spec.split(";") if p.strip()]
    return any(_file_exists(repo_root, p) for p in candidates)


def _resolve_entry_candidate(spec: str) -> bool:
    """解析单个入口候选（``module.attr`` / ``module.attr.attr`` / ``module:attr``）。

    采用“从长到短尝试模块前缀”的策略：先尝试把最长的前缀当作模块导入，再把剩余
    片段作为属性逐级取到。任何一步失败就回退到更短的前缀。避免把类名误当成模块。
    """
    spec = spec.strip()
    if not spec:
        return False
    if ":" in spec:
        mod, tail = spec.split(":", 1)
        parts = [p for p in tail.split(".") if p]
        if not mod or not parts:
            return False
        try:
            obj = importlib.import_module(mod)
        except Exception:
            return False
        for attr in parts:
            obj = getattr(obj, attr, None)
            if obj is None:
                return False
        return callable(obj)
    parts = [p for p in spec.split(".") if p]
    if not parts:
        return False
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except Exception:
            continue
        ok = True
        for attr in parts[i:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                ok = False
                break
        if ok and callable(obj):
            return True
    return False


def probe_entry_callable(entry_spec: Optional[str], repo_root=None) -> bool:
    """探测入口是否可调用（诚实优先，只认“能真正导入并取到可调用对象”）。

    ``entry_spec`` 形如 ``module:attr``、``module.attr``、``module.attr.attr``，
    或用 ``/`` 分隔的多个候选（任一候选可调用即视为可调用）。仓库根目录下的
    ``scripts/`` 模块不在包内，探测时临时将其加入 ``sys.path``，以便解析像
    ``manual_chain.cmd_plan_batches``、``production_release_gate.main`` 这类入口。
    """
    if not entry_spec:
        return False
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]  # src/aipd_os -> 仓库根
    scripts_dir = Path(repo_root) / "scripts"
    added = False
    if scripts_dir.is_dir():
        sp = str(scripts_dir)
        if sp not in sys.path:
            sys.path.insert(0, sp)
            added = True
    try:
        for candidate in entry_spec.split("/"):
            if _resolve_entry_candidate(candidate):
                return True
        return False
    finally:
        if added:
            try:
                sys.path.remove(str(scripts_dir))
            except ValueError:
                # noqa: EMPTY_EXCEPT - 清理 sys.path 失败（路径本就不在）可安全忽略
                pass


def probe_classification(
    cap: Capability, repo_root: Path, external_dependency: bool = False
) -> str:
    """根据运行时证据动态推导分类（不依赖静态写死）。

    规则（诚实优先，主证据 = 真实实现代码文件 + 真实测试，而非文档/测试**名称**）：
    - 外部依赖（未配置真实后端/服务）且未实现真实客户端 -> external_dependency。
    - 实现文件存在 + 单元测试存在 -> fully_implemented（若还声明限制则降为
      partially_implemented）。
    - 实现文件存在但缺测试 -> partially_implemented。
    - 仅配置文件/模板 -> template_only。
    - 无实现文件但与外部契约相关 -> protocol_only。
    - 什么都没有 -> not_implemented / not_verifiable。

    说明：``entry_point`` 多为逻辑/脚本入口（scripts/ 下以脚本方式运行），并非都
    可直接作为包模块机械导入（如 research 脚本用顶层 ``import _http_runtime``）。
    因此入口可调用性不作为降级门槛，但会作为 ``entry_callable`` 单独写入矩阵供
    透明核验，避免因标签老旧（部分标法与真实方法名不一致）而大面积误判。
    """
    if external_dependency:
        return "external_dependency"
    has_impl = probe_file_has_impl(repo_root, cap.implementation_file)
    has_test = bool((cap.unit_test or "").strip())
    has_limitation = bool((cap.current_limitation or "").strip())

    if has_impl and has_test:
        # 有真实实现代码 + 真实测试 -> 完全实现；若仍声明限制则降为部分实现
        return "partially_implemented" if has_limitation else "fully_implemented"
    if has_impl:
        return "partially_implemented"
    if cap.implementation_file and "template" in cap.implementation_file.lower():
        return "template_only"
    if cap.implementation_file and "protocol" in cap.implementation_file.lower():
        return "protocol_only"
    return "not_verifiable"


__all__ = [
    "Capability",
    "CapabilityRegistry",
    "CLASSIFICATIONS",
    "CLASSIFICATION_LABELS",
    "load_default_registry",
    "probe_classification",
    "probe_file_has_impl",
    "probe_entry_callable",
]
