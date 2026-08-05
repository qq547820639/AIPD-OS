"""对象存储：put/get/list/delete + 保留清理。"""
from __future__ import annotations

import os
import time

import pytest

from aipd_os.state.objects import ObjectStore


@pytest.fixture
def store(tmp_path):
    return ObjectStore(str(tmp_path / "objects"), retention_days=90)


def test_put_get_list_delete(store):
    store.put("proj1", "doc.txt", b"hello world")
    store.put("proj1", "img.png", b"\x89PNG")
    assert store.get("proj1", "doc.txt") == b"hello world"

    keys = [o["key"] for o in store.list("proj1")]
    assert set(keys) == {"doc.txt", "img.png"}

    store.delete("proj1", "doc.txt")
    assert [o["key"] for o in store.list("proj1")] == ["img.png"]


def test_tenant_isolated_dirs(store):
    store.put("proj1", "a.txt", b"tenant-default", tenant_id="t1")
    store.put("proj1", "a.txt", b"tenant-t2", tenant_id="t2")
    assert store.get("proj1", "a.txt", tenant_id="t1") == b"tenant-default"
    assert store.get("proj1", "a.txt", tenant_id="t2") == b"tenant-t2"


def test_retention_prune(store):
    store.put("proj1", "old.txt", b"old")
    store.put("proj1", "new.txt", b"new")  # 留下一个较新文件

    # 把 old.txt 的 mtime 改为很久以前
    d = store._dir("proj1", "default") / "old.txt"
    old = time.time() - 100 * 86400
    os.utime(d, (old, old))

    removed = store.retention_prune(age_days=30)
    assert removed == 1
    assert [o["key"] for o in store.list("proj1")] == ["new.txt"]
