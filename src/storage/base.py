from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        """初始化 SQLite store，输入数据库路径并保存为实例配置。"""
        self.db_path = str(Path(db_path))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """创建 SQLite 连接并配置 row_factory，返回可按列名读取的连接对象。"""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """提供事务上下文，yield SQLite 连接并在退出时提交或回滚。"""
        connection = self.get_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        """执行单条写入 SQL，输入 SQL 与参数元组，不返回查询结果。"""
        with self.transaction() as connection:
            connection.execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: list[tuple[Any, ...]]) -> None:
        """批量执行同一条写入 SQL，输入 SQL 与多组参数列表。"""
        with self.transaction() as connection:
            connection.executemany(sql, seq_of_parameters)

    def fetch_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """执行查询并返回第一行字典结果，未命中时返回 None。"""
        with self.get_connection() as connection:
            row = connection.execute(sql, parameters).fetchone()
        if row is None:
            return None
        return dict(row)

    def fetch_all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """执行查询并返回所有行的字典列表。"""
        with self.get_connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]
