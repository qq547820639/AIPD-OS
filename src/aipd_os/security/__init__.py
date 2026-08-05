"""AIPD-OS 安全模块（v5.0）。

提供三项安全能力：
1. **提示注入隔离**（``prompt_injection``）：把外部内容（附件、网页、论文正文）
   始终当作数据而非系统指令处理，检测并记录可疑指令，且外部内容永远不能修改
   成熟度门禁或安全策略。
2. **敏感数据权限与掩码**（``masking``）：对邮箱、电话、IP 及显式敏感值
   （supplier quote / contact / experiment_data）打码；敏感作用域要求显式授权。
3. **SBOM 生成**（``sbom``）：基于 ``pyproject.toml`` 生成确定性的
   CycloneDX 风格软件物料清单，无网络依赖。

本模块不依赖任何第三方库；可独立运行。
"""
from __future__ import annotations

from .masking import (
    PermissionError,
    can_access,
    classify_sensitive,
    mask_sensitive,
    require_mask,
)
from .prompt_injection import (
    detect_suspicious_instructions,
    external_never_controls_policy,
    is_external_content_allowed,
    log_suspect,
    sanitize_external_content,
)
from .sbom import generate_sbom, verify_sbom

__all__ = [
    "sanitize_external_content",
    "detect_suspicious_instructions",
    "external_never_controls_policy",
    "is_external_content_allowed",
    "log_suspect",
    "mask_sensitive",
    "classify_sensitive",
    "can_access",
    "require_mask",
    "PermissionError",
    "generate_sbom",
    "verify_sbom",
]