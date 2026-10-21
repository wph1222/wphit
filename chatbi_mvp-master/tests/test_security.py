from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import ChatBISystem
from database import DatabaseClient
from security import QuerySecurityManager, SecurityError, UserContext


class FakeCursor:
    def __init__(self):
        self.description = [
            ("customer_name",),
            ("customer_phone",),
            ("net_amount",),
        ]
        self.executed_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str):
        self.executed_sql = sql

    def fetchall(self):
        return [("宁德时代", "13800001111", 1250000)]


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_security_manager_rejects_non_select_sql():
    manager = QuerySecurityManager()
    user = UserContext(user_id="u_admin", role="admin")

    with pytest.raises(SecurityError, match="只允许执行查询语句"):
        manager.secure_sql("DELETE FROM sales_orders", user)


def test_security_manager_injects_region_filter_for_sales_role():
    manager = QuerySecurityManager()
    user = UserContext(user_id="u_sales_east", role="sales", region="华东大区")

    secured_sql = manager.secure_sql(
        """
        SELECT c.region, SUM(o.net_amount) AS revenue
        FROM sales_orders o
        JOIN dim_customers c ON o.customer_id = c.customer_id
        GROUP BY c.region
        """,
        user,
    )

    assert "c.region = '华东大区'" in secured_sql
    assert secured_sql.upper().count("WHERE") == 1


def test_security_manager_masks_sensitive_columns_for_sales_role():
    manager = QuerySecurityManager()
    user = UserContext(user_id="u_sales_east", role="sales", region="华东大区")

    masked_columns, masked_rows = manager.mask_result(
        columns=["customer_name", "customer_phone", "net_amount"],
        rows=[("宁德时代", "13800001111", 1250000)],
        user=user,
    )

    assert masked_columns == ["customer_name", "customer_phone", "net_amount"]
    assert masked_rows == [("宁德时代", "***", "***")]


def test_database_client_applies_security_before_query_execution():
    fake_connection = FakeConnection()
    client = DatabaseClient(connection_factory=lambda: fake_connection)
    user = UserContext(user_id="u_sales_east", role="sales", region="华东大区")

    columns, rows = client.execute(
        """
        SELECT c.customer_name, c.customer_phone, o.net_amount
        FROM sales_orders o
        JOIN dim_customers c ON o.customer_id = c.customer_id
        """,
        user=user,
    )

    assert "c.region = '华东大区'" in fake_connection.cursor_instance.executed_sql
    assert columns == ["customer_name", "customer_phone", "net_amount"]
    assert rows == [("宁德时代", "***", "***")]
    assert fake_connection.closed is True


def test_chatbi_system_returns_security_error_type():
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
            raise SecurityError(f"权限不足：{user.role}")

    system = ChatBISystem()
    system.parser = FakeParser()
    system.llm = FakeLLM()
    system.db = FakeDB()

    result = system.run(
        "查看订单明细",
        security_context=UserContext(user_id="u_sales_east", role="sales", region="华东大区"),
    )

    assert result["success"] is False
    assert result["error_type"] == "security"
    assert "sales" in result["error"]
