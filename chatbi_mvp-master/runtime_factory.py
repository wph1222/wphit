from __future__ import annotations

from dataclasses import dataclass

from config import APP_CONFIG, get_database_source_config
from database import DatabaseClient
from indicator_knowledge import IndicatorKnowledge
from llm_client import LLMClient
from query_parser import QueryParser
from result_formatter import ResultFormatter


@dataclass(slots=True)
class AppRuntime:
    source_id: str
    parser: QueryParser
    llm: LLMClient
    db: DatabaseClient
    formatter: ResultFormatter
    indicator_knowledge: IndicatorKnowledge


def build_database_client(app_config: dict | None = None, source_id: str | None = None) -> DatabaseClient:
    config = app_config or APP_CONFIG
    resolved_source_id = source_id or config["database"]["default_source"]
    db_config = get_database_source_config(resolved_source_id, config)
    return DatabaseClient(db_config=db_config, source_id=resolved_source_id)


def build_runtime(app_config: dict | None = None, source_id: str | None = None) -> AppRuntime:
    config = app_config or APP_CONFIG
    resolved_source_id = source_id or config["database"]["default_source"]
    return AppRuntime(
        source_id=resolved_source_id,
        parser=QueryParser(),
        llm=LLMClient(),
        db=build_database_client(config, resolved_source_id),
        formatter=ResultFormatter(),
        indicator_knowledge=IndicatorKnowledge(),
    )
