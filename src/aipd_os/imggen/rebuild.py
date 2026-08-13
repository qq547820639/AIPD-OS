"""失败页单页重建入口。

``rebuild_failed_pages`` 只重跑失败页，并**证明未修改页面的哈希保持不变**
（改前 / 改后哈希比对）。绝不重跑成功页。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable


def _sha_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rebuild_failed_pages(
    project: dict,
    failed_page_ids: list[str],
    pages_dir: str,
    rebuild_page: Callable[[str], bytes],
) -> dict:
    """只重跑失败页，证明未修改页面的哈希保持不变。

    Args:
        project: 项目状态 dict（仅用于记录，不修改）。
        failed_page_ids: 需要重建的失败页 id 列表。
        pages_dir: 页面 PNG 所在目录（``<pages_dir>/<pid>.png``）。
        rebuild_page: 生成某页新字节的回调，签名 ``rebuild_page(page_id) -> bytes``。

    Returns:
        报告：``{rebuilt, rebuilt_page_ids, unchanged_pages_verified,
        unexpected_changes, hash_preservation_ok, before_hashes, after_hashes}``。
    """
    pages_dir = Path(pages_dir)
    pages_dir.mkdir(parents=True, exist_ok=True)

    # 快照所有现存页面的哈希（改前）
    existing = sorted(p.stem for p in pages_dir.glob("*.png"))
    before = {pid: _sha_file(pages_dir / f"{pid}.png") for pid in existing}

    failed_set = set(failed_page_ids)
    # 只重建失败页，绝不触碰成功页
    rebuilt = []
    for pid in failed_page_ids:
        new_bytes = rebuild_page(pid)
        (pages_dir / f"{pid}.png").write_bytes(new_bytes)
        rebuilt.append(
            {
                "page_id": pid,
                "before_sha256": before.get(pid),
                "after_sha256": _sha_file(pages_dir / f"{pid}.png"),
            }
        )

    # 改后哈希
    after = {pid: _sha_file(pages_dir / f"{pid}.png") for pid in existing}

    # 未修改页：不在失败集内，且改前/改后哈希一致
    unchanged = {
        pid: h
        for pid, h in before.items()
        if pid not in failed_set and after.get(pid) == h
    }
    unexpected_changes = [
        pid for pid in before if pid not in failed_set and after.get(pid) != before.get(pid)
    ]

    return {
        "rebuilt": rebuilt,
        "rebuilt_page_ids": list(failed_page_ids),
        "unchanged_pages_verified": len(unchanged),
        "unexpected_changes": unexpected_changes,
        "hash_preservation_ok": len(unexpected_changes) == 0,
        "before_hashes": before,
        "after_hashes": after,
    }
