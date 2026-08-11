#!/usr/bin/env python3
"""兼容 wrapper：Supervisor 已迁移至 ``src/aipd_os/supervisor/``（P1-1）。

本文件只负责：
1. 独立运行时把仓库 src/ 加入 sys.path（包未 pip 安装时）；
2. 从 ``aipd_os.supervisor`` re-export 全部模块级名称（与原文件一致），
   保证旧引用（``from aipd_supervisor import Supervisor``）与 CLI 兼容。
runtime 包不依赖 scripts；本 wrapper 只 import aipd_os 包。
"""
from __future__ import annotations
import sys
from pathlib import Path

try:
    import aipd_os  # noqa: F401
except ImportError:
    # 独立运行脚本时，若包未 pip 安装，则将仓库 src/ 加入 sys.path
    _src = Path(__file__).resolve().parent.parent / 'src'
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

from aipd_os.supervisor import (  # noqa: E402
    PHASES,
    WORK_STATUSES,
    SCHEMA,
    Supervisor,
    now,
    jd,
    parser,
    main,
)

if __name__ == '__main__':
    sys.exit(main())
