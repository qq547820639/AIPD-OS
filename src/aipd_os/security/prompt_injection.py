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


# 外部内容不得请求发送/外泄敏感信息（防数据外泄 + 最小权限）
_SEND_SENSITIVE_VERBS = [
    "send", "share", "email", "forward", "transmit", "upload",
    "exfiltrate", "disclose", "leak", "release", "provide", "post",
]
_SENSITIVE_TARGETS = [
    "credentials", "password", "passwords", "api key", "api keys",
    "access token", "tokens", "secret", "secrets", "private key",
    "supplier quote", "quote", "contact", "phone number",
    "email address", "experiment data", "raw data", "database",
]


def external_cannot_send_sensitive_info(text: str) -> bool:
    """外部内容是否请求发送/外泄敏感信息。

    返回 True 表示文本试图让系统对外发送敏感信息，应被拒绝
    （最小权限 + 防数据外泄）。
    """
    if not text:
        return False
    lowered = text.lower()
    has_verb = any(v in lowered for v in _SEND_SENSITIVE_VERBS)
    has_target = any(t in lowered for t in _SENSITIVE_TARGETS)
    return has_verb and has_target


# 外部内容默认以最小权限运行：不得请求提权 / 扩大访问范围
_PRIVILEGE_ESCALATION = [
    "grant", "elevate", "elevated", "privilege", "privileges",
    "root access", "admin access", "administrator", "sudo",
    "full access", "unrestricted", "escalate", "give me access",
    "unlock access", "wider access", "all scopes", "wildcard access",
]


def external_cannot_escalate_privilege(text: str) -> bool:
    """外部内容是否请求提权（最小权限原则）。

    返回 True 表示文本试图提升权限 / 扩大访问范围，应被拒绝。
    """
    if not text:
        return False
    lowered = text.lower()
    return any(k in lowered for k in _PRIVILEGE_ESCALATION)


# 需要人工批准的高风险外部动作
_HIGH_RISK_ACTIONS = frozenset({
    "send_data_externally", "send_sensitive_info", "modify_maturity_gate",
    "modify_security_policy", "execute_system_command", "install_software",
    "delete_data", "modify_data", "external_network_call",
    "production_release", "privilege_escalation",
    "payment", "financial_transaction",
})


def requires_human_approval(action: str, text: str = "") -> bool:
    """判断外部动作是否属于高风险，需要人工批准。

    高风险动作（发送/外泄敏感信息、修改门禁或安全策略、提权、删除/修改数据、
    对外网络调用、生产发布、支付等）必须经过人工批准。

    :param action: 外部动作标识（见 ``_HIGH_RISK_ACTIONS``）
    :param text: 可选的触发内容，用于对未知动作做兜底判定
    """
    if action in _HIGH_RISK_ACTIONS:
        return True
    return bool(
        text
        and (
            external_cannot_send_sensitive_info(text)
            or external_never_controls_policy(text)
            or external_cannot_escalate_privilege(text)
        )
    )


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
    def _susp(line: str) -> bool:
        return bool(detect_suspicious_instructions(line)
                    or external_cannot_send_sensitive_info(line)
                    or external_cannot_escalate_privilege(line))
    clean_lines = [line for line in lines if not _susp(line)]
    held_out = [line for line in lines if _susp(line)]
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

    if external_cannot_send_sensitive_info(text):
        warnings.append(
            "external content requested sending sensitive information; denied "
            "(least privilege / no exfiltration)"
        )
    if external_cannot_escalate_privilege(text):
        warnings.append(
            "external content requested privilege escalation; denied (least privilege)"
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
    "external_cannot_send_sensitive_info",
    "external_cannot_escalate_privilege",
    "requires_human_approval",
    "is_external_content_allowed",
    "sanitize_external_content",
    "log_suspect",
]
