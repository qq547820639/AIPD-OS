"""重新生成仓库根目录的 RELEASE_MANIFEST.json（完整仓库可复现清单）。

以 ``git ls-files`` 为准（已跟踪文件），排除发布产物与本地生成物，
逐文件计算 size 与 SHA-256，并刷新版本/日期头字段。
用法：python scripts/regenerate_release_manifest.py [--version 5.4.0]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# 排除：清单自身、发布产物、虚拟环境、构建与缓存目录
# 注意：`.venv`（不带尾斜杠）同时覆盖 `.venv/` 与 `.venv-ci/`；
# 嵌套层级的 `*.dist-info/` 与 `__pycache__/` 由 _excluded() 额外排除
# （修复历史上 BUNDLE_MANIFEST.json 打包了 5.5.0 dist-info 残留的卫生问题）。
# 本脚本只负责生成清单本身，不重建现有 bundle —— 发布物重建是发布动作，
# 不在此阶段执行。
_EXCLUDE_PREFIXES = (
    # 发布证据文件彼此是“生成式证据”：SOURCE/BUNDLE/PROVENANCE/RELEASE 清单
    # 的内容会随清单生成而变化，若互相登记对方，任何一个重新生成都会使其余
    # 清单失效（自引用循环）。因此彼此互不登记，仅登记“确定的源文件集合”。
    "SOURCE_MANIFEST.json",
    "BUNDLE_MANIFEST.json",
    "PROVENANCE.json",
    "RELEASE_MANIFEST.json",
    "releases/",
    "build/",
    "dist/",
    ".venv",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "__pycache__/",
    "src/aipd_os.egg-info/",
    # 审计报告是生成式证据，内容随清单生成而变化，排除以打破循环哈希。
    "docs/audit/",
)


def _excluded(rel: str) -> bool:
    """判断相对路径是否应从清单中排除。

    除根级前缀外，还会排除任意嵌套层级的 ``*.dist-info`` 与 ``__pycache__``
    目录（pip/缓存可能把它们放在仓库内任意子目录）。
    """
    if rel.startswith(_EXCLUDE_PREFIXES):
        return True
    parts = rel.split("/")
    if any(p.endswith(".dist-info") for p in parts):
        return True
    if "__pycache__" in parts:
        return True
    return False


def _tracked_files(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="5.6.0")
    args = parser.parse_args()
    repo = _REPO

    files: list[dict] = []
    for rel in _tracked_files(repo):
        if _excluded(rel):
            continue
        p = repo / rel
        if not p.is_file():
            continue
        files.append({
            "path": rel,
            "size": p.stat().st_size,
            "sha256": _sha256(p),
        })
    files.sort(key=lambda e: e["path"])

    manifest = {
        "name": "aipd-orchestrator",
        "version": args.version,
        "release_date": date.today().isoformat(),
        "release_type": "AI full-chain product development and delivery supervisor",
        "theory_reference": "references/AIPD-OS-v4.0.docx",
        "files": files,
    }
    (repo / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RELEASE_MANIFEST.json 已刷新：{len(files)} 个文件，version={args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
