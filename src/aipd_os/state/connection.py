"""统一 SQLite 连接策略。

提供 ConnectionFactory 统一所有 SQLite 连接的 pragma 配置、
事务语义和错误映射。所有 store 应通过本模块获取连接，
而非各自调用 sqlite3.connect()。

P2-M1: Common DB Infrastructure
"""
from __future__ import annotations

import itertools
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

# ── 统一 pragma 配置 ──────────────────────────────────────────
# 所有 AIPD-OS SQLite 连接必须应用这些 pragma。
# WAL 模式暂不全局开启——需要在 Windows/macOS/Linux/共享文件系统
# 和 test isolation 场景验证后再决定。当前使用默认 DELETE journal。
# 注：连接等待/超时由 sqlite3.connect(timeout=...) 控制，
# SQLite 没有 ``PRAGMA timeout``（发出后被静默忽略，故不列入）。
_PRAGMAS: list[str] = [
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",       # 5s 等待锁
    "PRAGMA synchronous = NORMAL",       # 性能/安全平衡
]

# 活动事务登记表：key = (解析后的绝对路径, 线程 ident)。
# 按路径而非实例为 key，因为 store 常在每次 connect() 时新建一个
# ConnectionFactory（见 Supervisor.connect），实例级状态看不见外层事务。
_ACTIVE_TX: dict[tuple[str, int], sqlite3.Connection] = {}
_ACTIVE_LOCK = threading.Lock()
_SAVEPOINT_SEQ = itertools.count(1)


def _active_conn(key: tuple[str, int]) -> sqlite3.Connection | None:
    with _ACTIVE_LOCK:
        return _ACTIVE_TX.get(key)


class ConnectionFactory:
    """统一 SQLite 连接工厂。

    所有 store 通过 ``ConnectionFactory(path)`` 获取连接，
    保证 pragma 一致、row_factory 统一、事务边界清晰。
    """

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def _key(self) -> tuple[str, int]:
        return (str(self.path.resolve()), threading.get_ident())

    def connect(self) -> sqlite3.Connection:
        """创建新连接并应用统一 pragma。"""
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        for pragma in _PRAGMAS:
            conn.execute(pragma)
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """事务上下文管理器，同一 (库, 线程) 上可重入。

        用法::

            with factory.transaction() as conn:
                conn.execute("INSERT ...")
                conn.execute("UPDATE ...")
            # 自动 commit；异常自动 rollback

        重入时不再 ``BEGIN IMMEDIATE``（那会在同一进程的第二个连接上
        与自己的写锁死锁，5s 后抛 ``database is locked``），而是复用外层
        连接并开 SAVEPOINT：内层失败只回滚到该保存点，外层事务继续有效。
        """
        key = self._key
        outer = _active_conn(key)
        if outer is not None:
            name = f"aipd_sp_{next(_SAVEPOINT_SEQ)}"
            outer.execute(f"SAVEPOINT {name}")
            try:
                yield outer
            except Exception:
                outer.execute(f"ROLLBACK TO {name}")
                raise
            finally:
                outer.execute(f"RELEASE {name}")
            return
        conn = self.connect()
        with _ACTIVE_LOCK:
            _ACTIVE_TX[key] = conn
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_TX.pop(key, None)
            conn.close()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """非事务连接上下文：无活动事务时自开连接（语句级自动 commit）。

        用于只读查询或不需要原子性的单条写操作。
        同一 (库, 线程) 已有活动事务时改为复用该事务连接——在
        rollback-journal 模式下另开连接读取自己未提交的写会阻塞在写锁上，
        且此时语句不再自动 commit，而是随外层事务一起提交/回滚。
        """
        active = _active_conn(self._key)
        if active is not None:
            yield active
            return
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """对已有连接应用统一 pragma（兼容层）。"""
    for pragma in _PRAGMAS:
        conn.execute(pragma)
