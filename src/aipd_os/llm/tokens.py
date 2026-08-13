"""统一的 token 估算口径（全仓唯一实现）。

此前并存两套口径：``evals_runner/runner.py`` 用 ``len/3``、
``tool_adapters/_common.py`` 用 ``len//4``——同一文本在两处得到不同的
token 数。本模块收敛为唯一实现（约 4 字符/token 的保守启发式，兼容
中英文混排），所有估算点统一从这里导入。
"""

from __future__ import annotations

# 估算因子：约 4 字符/token（中英文混排的保守近似）。
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """按字符数估算 token 数（保守下限 1；估算值，非真实 usage）。"""
    return max(1, len(text or "") // CHARS_PER_TOKEN)


__all__ = ["CHARS_PER_TOKEN", "estimate_tokens"]
