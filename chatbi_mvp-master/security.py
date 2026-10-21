from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable


class SecurityError(Exception):
    """权限校验或 SQL 安全检查失败。"""


@dataclass(slots=True)
class UserContext:
    """当前请求的最小权限上下文。"""

    user_id: str
    role: str = "admin"
    region: str | None = None
    allowed_regions: list[str] = field(default_factory=list)

    @classmethod
    def demo_admin(cls) -> "UserContext":
        return cls(user_id="demo_admin", role="admin")


@dataclass(slots=True)
class SecurityPolicy:
    row_level_filters: list[tuple[str, str]] = field(default_factory=list)
    masked_columns: set[str] = field(default_factory=set)


class QuerySecurityManager:
    """负责 SQL 拦截、行级过滤和结果脱敏。"""

    _DANGEROUS_KEYWORDS = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|REPLACE)\b",
        flags=re.IGNORECASE,
    )
    _CLAUSE_BOUNDARY = re.compile(
        r"\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING)\b",
        flags=re.IGNORECASE,
    )

    def __init__(self):
        self.role_policies = {
            "admin": SecurityPolicy(),
            "finance": SecurityPolicy(
                masked_columns={"customer_phone", "customer_email"},
            ),
            "sales": SecurityPolicy(
                row_level_filters=[("dim_customers", "region")],
                masked_columns={
                    "customer_phone",
                    "customer_email",
                    "gross_amount",
                    "net_amount",
                    "material_cost",
                    "standard_cost",
                    "profit",
                },
            ),
        }

    def secure_sql(self, sql: str, user: UserContext | None = None) -> str:
        user_context = user or UserContext.demo_admin()
        normalized_sql = self._normalize_sql(sql)
        self._ensure_select_only(normalized_sql)

        policy = self._get_policy(user_context.role)
        secured_sql = normalized_sql
        for table_name, column_name in policy.row_level_filters:
            predicate = self._build_row_level_predicate(
                sql=secured_sql,
                table_name=table_name,
                column_name=column_name,
                user=user_context,
            )
            if predicate:
                secured_sql = self._append_predicate(secured_sql, predicate)

        return secured_sql

    def mask_result(
        self,
        columns: list[str],
        rows: Iterable[tuple | list],
        user: UserContext | None = None,
    ) -> tuple[list[str], list[tuple]]:
        user_context = user or UserContext.demo_admin()
        policy = self._get_policy(user_context.role)
        if not policy.masked_columns:
            return columns, [tuple(row) for row in rows]

        sensitive_indexes = {
            index
            for index, column in enumerate(columns)
            if column.lower() in policy.masked_columns
        }
        if not sensitive_indexes:
            return columns, [tuple(row) for row in rows]

        masked_rows: list[tuple] = []
        for row in rows:
            values = list(row)
            for index in sensitive_indexes:
                values[index] = "***"
            masked_rows.append(tuple(values))

        return columns, masked_rows

    def _get_policy(self, role: str) -> SecurityPolicy:
        return self.role_policies.get(role.lower(), self.role_policies["admin"])

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        normalized = sql.strip()
        normalized = re.sub(r"^```sql\s*|```$", "", normalized, flags=re.IGNORECASE)
        normalized = normalized.strip()
        return normalized[:-1].strip() if normalized.endswith(";") else normalized

    def _ensure_select_only(self, sql: str) -> None:
        if not sql:
            raise SecurityError("SQL 不能为空。")
        if sql.count(";") > 0:
            raise SecurityError("检测到多语句执行风险。")
        if self._DANGEROUS_KEYWORDS.search(sql):
            raise SecurityError("只允许执行查询语句。")
        if not re.match(r"^\s*(SELECT|WITH)\b", sql, flags=re.IGNORECASE):
            raise SecurityError("只允许执行查询语句。")

    def _build_row_level_predicate(
        self,
        sql: str,
        table_name: str,
        column_name: str,
        user: UserContext,
    ) -> str | None:
        if user.role.lower() == "sales" and not user.region:
            raise SecurityError("销售角色缺少区域权限信息。")

        value = user.region
        if not value:
            return None

        if not self._contains_table(sql, table_name):
            return None

        qualifier = self._find_table_qualifier(sql, table_name)
        return f"{qualifier}.{column_name} = '{self._escape_sql_literal(value)}'"

    @staticmethod
    def _contains_table(sql: str, table_name: str) -> bool:
        return re.search(
            rf"\b(?:FROM|JOIN)\s+{re.escape(table_name)}\b",
            sql,
            flags=re.IGNORECASE,
        ) is not None

    @staticmethod
    def _find_table_qualifier(sql: str, table_name: str) -> str:
        pattern = re.compile(
            rf"\b(?:FROM|JOIN)\s+{re.escape(table_name)}(?:\s+(?:AS\s+)?([a-zA-Z_][\w]*))?",
            flags=re.IGNORECASE,
        )
        match = pattern.search(sql)
        alias = match.group(1) if match else None
        return alias or table_name

    def _append_predicate(self, sql: str, predicate: str) -> str:
        boundary = self._CLAUSE_BOUNDARY.search(sql)
        insert_at = boundary.start() if boundary else len(sql)
        prefix = sql[:insert_at].rstrip()
        suffix = sql[insert_at:].lstrip()
        joiner = " AND " if re.search(r"\bWHERE\b", prefix, flags=re.IGNORECASE) else " WHERE "
        updated = f"{prefix}{joiner}{predicate}"
        if suffix:
            updated = f"{updated} {suffix}"
        return updated

    @staticmethod
    def _escape_sql_literal(value: str) -> str:
        return value.replace("'", "''")
