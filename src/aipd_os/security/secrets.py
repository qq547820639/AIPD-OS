"""安全凭据存储与脱敏工具。

提供两项能力：

1. **凭据登记（不落盘加密）**：:class:`SecretStore` 只登记环境变量名称
   （env var reference），绝不把明文凭据写入任何文件；解密统一从环境变量在
   需要时读取，保持“密钥不落盘”的安全边界。
2. **值脱敏**：:func:`mask_secret` 只保留首尾字符，中间以 ``*`` 代替，用于
   日志/结构化输出中避免泄露完整 token / API key / 凭据。

本模块不引入任何第三方依赖；可独立运行。
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, Dict, List, Optional

# 凭据类别的常见环境变量名后缀集合（用于判定一个变量是否疑似敏感）
SENSITIVE_SUFFIXES = (
    "_KEY", "_SECRET", "_TOKEN", "_PASSWORD", "_API_KEY",
    "_CREDENTIALS", "_AUTH", "_PASSPHRASE", "_PRIVATE",
)

# 常见敏感变量名（精确匹配）
SENSITIVE_EXACT = frozenset({
    "AIPD_DATA_ENCRYPTION_KEY",
    "AIPD_EVAL_MODEL_ENDPOINT_API_KEY",
    "AIPD_MAIL_PASSWORD",
    "AIPD_MAIL_SMTP_PASSWORD",
    "AIPD_MAIL_IMAP_PASSWORD",
    "AIPD_IMGGEN_API_KEY",
    "AIPD_VISION_API_KEY",
})

# 独立敏感关键词（用于嵌套结构中的字段名，如 SECRET / TOKEN / API_KEY）
SENSITIVE_KEYWORDS = frozenset({
    "SECRET", "TOKEN", "PASSWORD", "PASSPHRASE",
    "API_KEY", "APIKEY", "CREDENTIALS", "AUTH", "PRIVATE_KEY",
})


def mask_secret(value: Any) -> str:
    """对敏感值脱敏：只保留首尾字符，其余为 ``*``。

    - 空串 / None 原样返回；
    - 长度 <= 2 时全部打 ``*``；
    - 长度 3..4 仅保留首个字符；
    - 长度 >= 5 保留首尾各一个字符，中间全部 ``*``。

    :param value: 待脱敏的凭据值
    """
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    n = len(s)
    if n == 1:
        return "*"
    if n <= 4:
        return s[0] + "*" * (n - 1)
    return s[0] + "*" * (n - 2) + s[-1]


def is_sensitive_var(name: str) -> bool:
    """判断环境变量名/字段名是否疑似敏感（精确 / 后缀 / 独立关键词）。"""
    upper = name.upper()
    if upper in SENSITIVE_EXACT:
        return True
    if upper in SENSITIVE_KEYWORDS:
        return True
    return any(upper.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


class SecretStore:
    """凭据登记表：只登记环境变量名，不落盘明文。

    对外暴露 ``registered``、``register``、``read``、``masked`` 与医生体检
    所需的 ``status()`` / ``masked_samples()``。
    """

    def __init__(self) -> None:
        #: 已登记的环境变量名 -> 用途说明
        self._registry: Dict[str, str] = {}

    def register(self, env_name: str, purpose: str = "") -> None:
        """登记一个环境变量名（不读取、不落盘其值）。"""
        if not env_name:
            raise ValueError("env_name must be non-empty")
        self._registry[env_name] = purpose

    def unregister(self, env_name: str) -> None:
        self._registry.pop(env_name, None)

    def registered(self) -> List[str]:
        return list(self._registry.keys())

    def is_registered(self, env_name: str) -> bool:
        return env_name in self._registry

    def read(self, env_name: str) -> Optional[str]:
        """从环境变量读取凭据明文（运行期按需读取，不缓存不落盘）。"""
        return os.environ.get(env_name)

    def exposed(self, env_name: str) -> bool:
        """该环境变量当前是否已设置（存在凭据）。"""
        return env_name in os.environ

    def masked(self, env_name: str) -> Optional[str]:
        """读取并脱敏后的值；未设置返回 None。"""
        value = self.read(env_name)
        if value is None:
            return None
        return mask_secret(value)

    def status(self) -> List[Dict[str, Any]]:
        """返回医生体检用的状态列表。

        每项：``{"env": name, "registered": bool, "set": bool, "purpose": str}``。
        """
        out: List[Dict[str, Any]] = []
        for name in sorted(self._registry):
            out.append({
                "env": name,
                "registered": True,
                "set": self.exposed(name),
                "purpose": self._registry[name],
                "masked": self.masked(name),
            })
        return out

    def masked_samples(self) -> Dict[str, str]:
        """返回 ``env -> masked value``，供审计展示（绝不含明文）。"""
        return {name: (self.masked(name) or ("" if not self.exposed(name) else "***"))
                for name in self._registry}


def mask_secret_deep(data: Any, secret_names: Optional[Iterable[str]] = None) -> Any:
    """对数据结构中的敏感字段脱敏（递归遍历 dict/list）。

    对 dict 中值非 None 的字段，若字段名满足 :func:`is_sensitive_var`，
    则用 :func:`mask_secret` 替换其值；嵌套的 dict/list 会递归处理。
    适合对结构化日志/指标做脱敏兜底。
    """
    if isinstance(data, dict):
        names = set(secret_names or ())
        out: Dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, (str, int, float)) and v is not None:
                if k in names or is_sensitive_var(str(k)):
                    out[k] = mask_secret(v)
                    continue
                out[k] = v
            elif isinstance(v, (dict, list)):
                out[k] = mask_secret_deep(v, secret_names)
            else:
                out[k] = v
        return out
    if isinstance(data, list):
        return [mask_secret_deep(item, secret_names) for item in data]
    return data


__all__ = [
    "SENSITIVE_SUFFIXES",
    "SENSITIVE_EXACT",
    "mask_secret",
    "is_sensitive_var",
    "SecretStore",
    "mask_secret_deep",
]
