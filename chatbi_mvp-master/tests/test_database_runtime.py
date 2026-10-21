from pathlib import Path
import sys

import pymysql
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import (
    DatabaseClient,
    DatabaseConnectionPool,
    QueryExecutionError,
)
from security import UserContext


class ExplainableCursor:
    def __init__(self):
        self.description = [("region",), ("revenue",)]
        self.executed_sqls = []
        self._last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str):
        self.executed_sqls.append(sql)
        self._last_sql = sql
        if sql.startswith("EXPLAIN "):
            self.description = [("id",), ("select_type",), ("table",), ("type",), ("key",)]
        else:
            self.description = [("region",), ("revenue",)]

    def fetchall(self):
        if self._last_sql.startswith("EXPLAIN "):
            return [(1, "SIMPLE", "sales_orders", "ALL", None)]
        return [("华东大区", 1250000)]


class SyntaxErrorCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str):
        raise pymysql.err.ProgrammingError(1064, "You have an error in your SQL syntax")

    def fetchall(self):
        return []


class TimedOutCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str):
        raise pymysql.err.OperationalError(
            2013,
            "Lost connection to MySQL server during query (The read operation timed out)",
        )

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True

    def ping(self, reconnect=False):
        return None


def test_database_client_classifies_sql_syntax_errors():
    client = DatabaseClient(connection_factory=lambda: FakeConnection(SyntaxErrorCursor()))

    with pytest.raises(QueryExecutionError) as exc_info:
        client.execute("SELECT broken FROM sales_orders")

    assert exc_info.value.error_type == "sql_syntax"
    assert exc_info.value.metadata["error_code"] == 1064


def test_database_client_classifies_connection_factory_errors():
    client = DatabaseClient(
        connection_factory=lambda: (_ for _ in ()).throw(
            pymysql.err.OperationalError(
                1045,
                "Access denied for user 'chatbi'@'localhost' (using password: YES)",
            )
        )
    )

    with pytest.raises(QueryExecutionError) as exc_info:
        client.execute("SELECT * FROM sales_orders")

    assert exc_info.value.error_type == "permission_denied"
    assert exc_info.value.metadata["error_code"] == 1045


def test_database_client_records_explain_for_slow_queries():
    time_points = iter([10.0, 10.25])
    client = DatabaseClient(
        connection_factory=lambda: FakeConnection(ExplainableCursor()),
        slow_query_threshold_ms=100,
        time_fn=lambda: next(time_points),
    )

    columns, rows = client.execute(
        "SELECT region, SUM(net_amount) AS revenue FROM sales_orders GROUP BY region",
        user=UserContext(user_id="u_admin", role="admin"),
    )

    assert columns == ["region", "revenue"]
    assert rows == [("华东大区", 1250000)]
    assert client.last_query_info["duration_ms"] == 250.0
    assert client.last_query_info["slow_query"] is True
    assert client.last_query_info["explain_plan"][0]["table"] == "sales_orders"


def test_database_client_classifies_read_timeout_as_query_timeout():
    client = DatabaseClient(connection_factory=lambda: FakeConnection(TimedOutCursor()))

    with pytest.raises(QueryExecutionError) as exc_info:
        client.execute("SELECT SLEEP(2)")

    assert exc_info.value.error_type == "query_timeout"
    assert exc_info.value.metadata["error_code"] == 2013


def test_connection_pool_reuses_idle_connections():
    created = []

    def connection_factory():
        conn = FakeConnection(ExplainableCursor())
        created.append(conn)
        return conn

    pool = DatabaseConnectionPool(
        connection_factory=connection_factory,
        pool_size=1,
    )

    first = pool.acquire()
    pool.release(first)
    second = pool.acquire()

    assert first is second
    assert len(created) == 1
    pool.release(second)
    pool.close_all()


def test_chatbi_system_returns_granular_database_error_type_for_timeout():
    from main import ChatBISystem

    class FakeParser:
        def parse(self, question: str) -> str:
            return question

        def validate(self, parsed: str) -> bool:
            return True

    class FakeLLM:
        def generate_sql(self, _system_msg: str, _prompt: str) -> str:
            return "SELECT * FROM sales_orders"

    class FakeDB:
        def execute(self, sql: str, user=None):
            raise QueryExecutionError(
                "query_timeout",
                "SQL 执行超时，请缩小时间范围后重试",
                metadata={"duration_ms": 3100.0},
            )

    system = ChatBISystem()
    system.parser = FakeParser()
    system.llm = FakeLLM()
    system.db = FakeDB()

    result = system.run("查看最近 12 个月订单明细")

    assert result["success"] is False
    assert result["error_type"] == "database_query_timeout"
    assert result["metadata"]["db_duration_ms"] == 3100.0
