"""提示注入隔离。

设计原则：**外部内容（附件、网页、论文正文等）始终是数据，永远不是系统指令**。

- ``sanitize_external_content``：净化外部内容，剥离/标记可疑指令，结果只做为数据
  使用，绝不注入系统提示词；
- ``detect_suspicious_instructions``：基于正则 + 关键词启发式检测可疑指令模式；
- ``external_never_controls_policy``：外部内容不得修改成熟度门禁或安全策略；
- ``is_external_content_allowed``：外部内容在某些作用域（门禁/安全策略）下被禁止；
- ``log_suspect``：记录可疑事件到结构化日志。

本模块不依赖任何第三方库。
"""
from __future__ import annotations

import base64
import logging
import re
from typing import List, Optional

from aipd_os.logging_utils import log_event

# 外部内容来源类型
ALLOWED_SOURCE_TYPES = frozenset({"attachment", "web_page", "paper_text", "document"})

# 明确的可疑指令模式（正则，大小写不敏感）
_SUSPICIOUS_PATTERNS: List[re.Pattern] = [
    re.compile(r"ignore\s+(previous|prior|all)\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+your\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"act\s+(as|like)\s+", re.IGNORECASE),
    re.compile(r"your\s+new\s+(role|instruction|system\s+prompt)", re.IGNORECASE),
    re.compile(r"system\s*[:：]", re.IGNORECASE),
    re.compile(r"override", re.IGNORECASE),
    re.compile(r"disregard\s+your\s+policy", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)", re.IGNORECASE),
    re.compile(r"higher\s+priority\s+than", re.IGNORECASE),
    re.compile(r"above\s+all\s+(previous|other)\s+instructions", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all\s+previous)", re.IGNORECASE),
    re.compile(r"from\s+now\s+on\s*,\s*you", re.IGNORECASE),
    re.compile(r"do\s+not\s+(obey|follow)\s+", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"print\s+(your|the)\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"set\s+(the\s+)?gate\s+to\s+(c\d|C\d)", re.IGNORECASE),
    re.compile(r"set\s+(the\s+)?maturity\s+gate", re.IGNORECASE),
    re.compile(r"allow\s+override", re.IGNORECASE),
    re.compile(r"bypass\s+(the\s+)?(gate|policy|review)", re.IGNORECASE),
    re.compile(r"mark\s+(as\s+)?(approved|passed)\b", re.IGNORECASE),
]

# 外部内容不得控制的门禁/安全策略关键词（与命令式动词组合）
_POLICY_KEYWORDS = [
    "maturity gate", "maturity gates", "security policy", "release gate",
    "production release", "gate to", "set gate", "allow override",
    "approve gate", "pass gate", "change policy", "set c7", "set c6",
]
_IMPERATIVE_VERBS = [
    "set", "allow", "approve", "pass", "change", "override", "mark",
    "grant", "unlock", "bypass", "release", "enable", "raise",
]

# 编码指令（base64 / 十六进制）启发式
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{36,}={0,2}\b")
_HEX_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}){16,}\b")


def _category_for(pattern: re.Pattern) -> str:
    """把正则映射为可读的分类名，便于日志与告警。"""
    src = pattern.pattern
    if "ignore" in src or "forget" in src or "disregard" in src:
        return "instruction_override"
    if "system" in src or "prompt" in src or "reveal" in src or "print" in src:
        return "system_prompt_manipulation"
    if "you are" in src or "act as" in src or "new role" in src:
        return "role_hijack"
    if "gate" in src or "maturity" in src or "override" in src or "bypass" in src \
            or "approve" in src or "mark" in src:
        return "policy_override"
    return "suspicious"


def detect_suspicious_instructions(text: str) -> List[str]:
    """检测并返回可疑指令模式列表（每个元素为 ``category: matched_text``）。

    使用正则 + 关键词启发式。该函数只做检测，不修改文本。
    """
    if not text:
        return []
    detected: List[str] = []
    lowered = text.lower()

    for pattern in _SUSPICIOUS_PATTERNS:
        for m in pattern.findall(text):
            snippet = m if isinstance(m, str) else " ".join(x for x in m if x)
            detected.append(f"{_category_for(pattern)}: {snippet[:80]}")
            break  # 每个正则最多报一次

    # 编码指令启发式
    if _B64_RE.search(text):
        detected.append("encoded_instruction: possible base64 payload")
    if _HEX_RE.search(text):
        detected.append("encoded_instruction: possible hex payload")

    # 门禁/安全策略控制尝试
    for kw in _POLICY_KEYWORDS:
        if kw in lowered:
            # 需要命令式动词，避免把中性描述当指令
            if any(v in lowered for v in _IMPERATIVE_VERBS):
                detected.append(f"policy_override: external content references {kw!r}")
                break

    # 去重（保持顺序）
    seen = set()
    unique = []
    for d in detected:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


def external_never_controls_policy(text: str) -> bool:
    """外部内容是否尝试修改成熟度门禁或安全策略。

    返回 True 表示文本试图改变门禁或安全策略（应被拒绝）。
    """
    if not text:
        return False
    lowered = text.lower()
    for kw in _POLICY_KEYWORDS:
        if kw in lowered:
            if any(v in lowered for v in _IMPERATIVE_VERBS):
                return True
    return False


def is_external_content_allowed(kind: str) -> bool:
    """外部内容是否允许用于该作用域。

    外部内容永远不能修改成熟度门禁或安全策略，因此对 ``maturity_gate`` 与
    ``security_policy`` 两类作用域返回 False。
    """
    if kind in ("maturity_gate", "security_policy"):
        return False
    return True


def sanitize_external_content(
    text: str,
    source_type: str = "document",
    logger: Optional[logging.Logger] = None,
) -> dict:
    """净化外部内容。

    外部内容始终作为数据处理，绝不作为系统指令。任何被识别为可疑指令的片段
    都会从结果中剥离，并记录到 ``detected_suspicious`` 与 ``warnings``。

    :param text: 外部输入文本
    :param source_type: 来源类型（attachment / web_page / paper_text / document）
    :param logger: 可选 logger，用于上报可疑事件
    :returns: ``{"sanitized_text", "detected_suspicious", "warnings"}``
    """
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "document"
    if not text:
        return {"sanitized_text": text or "", "detected_suspicious": [], "warnings": []}

    suspicious = detect_suspicious_instructions(text)
    warnings: List[str] = []
    lines = text.split("\n")
    held_out: List[str] = []

    # 剥离含可疑指令的行：外部内容永远不进入系统指令通道
    clean_lines = [line for line in lines if not detect_suspicious_instructions(line)]
    held_out = [line for line in lines if detect_suspicious_instructions(line)]
    sanitized = "\n".join(clean_lines)

    if suspicious:
        warnings.append(
            f"suspicious instructions detected and isolated for {source_type}; "
            f"held_out_lines={len(held_out)}"
        )
        warnings.extend(f"suspicious: {s}" for s in suspicious)

    if external_never_controls_policy(text):
        warnings.append(
            "external content attempted to change maturity gate or security policy; "
            "change denied"
        )

    if held_out and logger is not None:
        log_suspect(logger, source_type, text, suspicious)

    return {
        "sanitized_text": sanitized,
        "detected_suspicious": suspicious,
        "warnings": warnings,
    }


def log_suspect(logger: logging.Logger, kind: str, text: str, reasons: List[str]) -> None:
    """把可疑外部内容写入结构化日志事件。"""
    log_event(
        logger,
        "security.suspect_content",
        kind=kind,
        reasons=reasons,
        length=len(text),
    )


__all__ = [
    "ALLOWED_SOURCE_TYPES",
    "detect_suspicious_instructions",
    "external_never_controls_policy",
    "is_external_content_allowed",
    "sanitize_external_content",
    "log_suspect",
]
