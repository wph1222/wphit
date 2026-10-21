"""
数据库模块

负责数据库连接、SQL 执行和结果获取。
将数据库操作封装为独立模块，便于后续扩展（如连接池、读写分离等）。
"""

from __future__ import annotations

import logging
from queue import Empty, LifoQueue
from time import perf_counter
from typing import Any, Callable

import pymysql

from config import APP_CONFIG, DB_RUNTIME_CONFIG, get_database_source_config
from security import QuerySecurityManager, UserContext

logger = logging.getLogger("chatbi.database")


class QueryExecutionError(RuntimeError):
    """数据库执行失败后的统一异常。"""

    def __init__(
        self,
        error_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.metadata = metadata or {}


class DatabaseConnectionPool:
    """轻量连接池，优先复用空闲连接，避免每次查询重新建连。"""

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        pool_size: int,
        max_overflow: int = 0,
        pool_timeout: float = 3.0,
    ):
        self.connection_factory = connection_factory
        self.pool_size = max(pool_size, 1)
        self.max_overflow = max(max_overflow, 0)
        self.pool_timeout = pool_timeout
        self._idle_connections: LifoQueue[Any] = LifoQueue(maxsize=self.pool_size)
        self._total_connections = 0

    def acquire(self) -> Any:
        try:
            conn = self._idle_connections.get_nowait()
        except Empty:
            if self._total_connections < self.pool_size + self.max_overflow:
                conn = self.connection_factory()
                self._total_connections += 1
                return conn
            conn = self._idle_connections.get(timeout=self.pool_timeout)

        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:
            self._discard_connection(conn)
            conn = self.connection_factory()
            self._total_connections += 1
            return conn

    def release(self, conn: Any) -> None:
        try:
            self._idle_connections.put_nowait(conn)
        except Exception:
            self._discard_connection(conn)

    def close_all(self) -> None:
        while True:
            try:
                conn = self._idle_connections.get_nowait()
            except Empty:
                break
            self._discard_connection(conn)

    def _discard_connection(self, conn: Any) -> None:
        try:
            conn.close()
        finally:
            self._total_connections = max(self._total_connections - 1, 0)


class DatabaseClient:
    """MySQL 数据库客户端"""

    def __init__(
        self,
        db_config: dict[str, Any] | None = None,
        source_id: str | None = None,
        connection_factory: Callable[[], Any] | None = None,
        security_manager: QuerySecurityManager | None = None,
        slow_query_threshold_ms: float | None = None,
        time_fn: Callable[[], float] | None = None,
        connection_pool: DatabaseConnectionPool | None = None,
    ):
        self.source_id = source_id or APP_CONFIG["database"]["default_source"]
        self.config = db_config or get_database_source_config(self.source_id)
        self.security = security_manager or QuerySecurityManager()
        self.time_fn = time_fn or perf_counter
        self.slow_query_threshold_ms = (
            slow_query_threshold_ms
            if slow_query_threshold_ms is not None
            else DB_RUNTIME_CONFIG["slow_query_threshold_ms"]
        )
        self.connection_factory = connection_factory
        self.connection_pool = connection_pool
        self.last_query_info: dict[str, Any] = {}

        if self.connection_factory is None and self.connection_pool is None:
            self.connection_pool = DatabaseConnectionPool(
                connection_factory=lambda: pymysql.connect(**self._connection_kwargs()),
                pool_size=DB_RUNTIME_CONFIG["pool_size"],
                max_overflow=DB_RUNTIME_CONFIG["max_overflow"],
                pool_timeout=DB_RUNTIME_CONFIG["pool_timeout"],
            )

    def execute(
        self,
        sql: str,
        user: UserContext | None = None,
    ) -> tuple[list[str], list[tuple]]:
        """
        执行 SQL 并返回结果

        Args:
            sql: 待执行的 SQL 语句

        Returns:
            (列名列表, 结果行列表)
        """
        user_context = user or UserContext.demo_admin()
        secured_sql = self.security.secure_sql(sql, user_context)
        started_at = self.time_fn()
        conn = None
        try:
            conn = self._acquire_connection()
            with conn.cursor() as cursor:
                cursor.execute(secured_sql)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                results = cursor.fetchall()
                duration_ms = round((self.time_fn() - started_at) * 1000, 2)
                explain_plan = self._explain(cursor, secured_sql, duration_ms)
                self.last_query_info = {
                    "sql": secured_sql,
                    "duration_ms": duration_ms,
                    "slow_query": bool(explain_plan),
                    "explain_plan": explain_plan,
                }
                if explain_plan:
                    logger.warning(
                        "Slow query detected: duration_ms=%s sql=%s",
                        duration_ms,
                        secured_sql,
                    )
                _, masked_rows = self.security.mask_result(columns, results, user_context)
                return columns, masked_rows
        except (pymysql.MySQLError, OSError) as exc:
            duration_ms = round((self.time_fn() - started_at) * 1000, 2)
            self.last_query_info = {
                "sql": secured_sql,
                "duration_ms": duration_ms,
                "slow_query": False,
                "explain_plan": [],
            }
            raise self._translate_db_error(exc, secured_sql, duration_ms) from exc
        finally:
            if conn is not None:
                self._release_connection(conn)

    def validate_connection(self) -> bool:
        """验证数据库连接是否正常"""
        try:
            conn = self._acquire_connection()
            self._release_connection(conn)
            return True
        except Exception:
            return False

    def _acquire_connection(self) -> Any:
        if self.connection_pool is not None:
            return self.connection_pool.acquire()
        if self.connection_factory is None:
            raise RuntimeError("数据库连接工厂未初始化")
        return self.connection_factory()

    def _release_connection(self, conn: Any) -> None:
        if self.connection_pool is not None:
            self.connection_pool.release(conn)
        else:
            conn.close()

    def _connection_kwargs(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.config.items()
            if key not in {"driver", "name"}
        }

    def _explain(self, cursor: Any, sql: str, duration_ms: float) -> list[dict[str, Any]]:
        if duration_ms < self.slow_query_threshold_ms:
            return []
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            return []
        try:
            cursor.execute(f"EXPLAIN {sql}")
            explain_columns = [desc[0] for desc in cursor.description] if cursor.description else []
            explain_rows = cursor.fetchall()
            return [
                dict(zip(explain_columns, row))
                for row in explain_rows
            ]
        except Exception as exc:
            logger.warning("Failed to capture EXPLAIN plan: %s", exc)
            return []

    def _translate_db_error(
        self,
        exc: Exception,
        sql: str,
        duration_ms: float,
    ) -> QueryExecutionError:
        error_code = exc.args[0] if getattr(exc, "args", None) else None
        error_text = str(exc)
        metadata = {
            "sql": sql,
            "duration_ms": duration_ms,
            "error_code": error_code,
            "raw_error": error_text,
        }

        if isinstance(exc, pymysql.err.ProgrammingError) or error_code == 1064:
            return QueryExecutionError(
                "sql_syntax",
                "SQL 语法错误，请检查字段、聚合和别名是否正确",
                metadata,
            )
        if error_code in {1044, 1045, 1142, 1143, 1227}:
            return QueryExecutionError(
                "permission_denied",
                "数据库拒绝执行该查询，请检查当前账号权限",
                metadata,
            )
        if error_code in {1205, 3024} or (
            error_code in {2013}
            and "timed out" in error_text.lower()
        ):
            return QueryExecutionError(
                "query_timeout",
                "SQL 执行超时，请缩小时间范围或减少返回列后重试",
                metadata,
            )
        if isinstance(exc, OSError) or error_code in {2003, 2006, 2013}:
            return QueryExecutionError(
                "connection_error",
                "数据库连接失败，请检查连接池和数据库状态",
                metadata,
            )
        return QueryExecutionError(
            "execution_error",
            f"SQL 执行失败：{error_text}",
            metadata,
        )
