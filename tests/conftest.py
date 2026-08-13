"""让测试在未安装包的情况下也能导入 src 目录下的源码。"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
