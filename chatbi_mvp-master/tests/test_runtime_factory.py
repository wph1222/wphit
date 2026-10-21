from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_build_runtime_uses_requested_database_source(monkeypatch):
    import runtime_factory

    captured = {}

    class FakeParser:
        pass

    class FakeLLM:
        pass

    class FakeFormatter:
        pass

    class FakeIndicatorKnowledge:
        pass

    class FakeDatabaseClient:
        def __init__(self, db_config=None, source_id=None):
            captured["db_config"] = db_config
            captured["source_id"] = source_id

    monkeypatch.setattr(runtime_factory, "QueryParser", FakeParser)
    monkeypatch.setattr(runtime_factory, "LLMClient", FakeLLM)
    monkeypatch.setattr(runtime_factory, "ResultFormatter", FakeFormatter)
    monkeypatch.setattr(runtime_factory, "IndicatorKnowledge", FakeIndicatorKnowledge)
    monkeypatch.setattr(runtime_factory, "DatabaseClient", FakeDatabaseClient)

    app_config = {
        "database": {
            "default_source": "mysql_main",
            "sources": {
                "mysql_main": {"driver": "mysql", "host": "localhost", "port": 3307},
                "finance_pg": {"driver": "postgresql", "host": "localhost", "port": 5432},
            },
        }
    }

    runtime = runtime_factory.build_runtime(app_config, source_id="finance_pg")

    assert runtime.source_id == "finance_pg"
    assert captured["source_id"] == "finance_pg"
    assert captured["db_config"]["driver"] == "postgresql"


def test_chatbi_system_run_uses_runtime_factory_for_source_id():
    from main import ChatBISystem
    from security import UserContext

    captured = {}

    class FakeParser:
        def parse(self, question: str) -> str:
            return question

        def validate(self, parsed: str) -> bool:
            return True

    class FakeLLM:
        def generate_sql(self, _system_msg: str, _prompt: str) -> str:
            return "SELECT 1"

    class FakeDB:
        last_query_info = {"duration_ms": 12.5, "slow_query": False, "explain_plan": []}

        def execute(self, sql: str, user=None):
            captured["sql"] = sql
            captured["user"] = user
            return ["value"], [(1,)]

    class FakeFormatter:
        def format(self, columns, rows) -> str:
            return "ok"

    class FakeIndicatorKnowledge:
        def get_indicator_context(self, question: str):
            return {"detected_indicators": [], "indicator_block": ""}

    def fake_runtime_factory(app_config, source_id=None):
        captured["source_id"] = source_id
        return SimpleNamespace(
            source_id=source_id or "mysql_main",
            parser=FakeParser(),
            llm=FakeLLM(),
            db=FakeDB(),
            formatter=FakeFormatter(),
            indicator_knowledge=FakeIndicatorKnowledge(),
        )

    system = ChatBISystem(app_config={"features": {}}, runtime_factory=fake_runtime_factory)

    result = system.run(
        "查看总订单数",
        source_id="finance_pg",
        security_context=UserContext(user_id="u1", role="finance"),
    )

    assert result["success"] is True
    assert captured["source_id"] == "finance_pg"
    assert result["metadata"]["source_id"] == "finance_pg"

