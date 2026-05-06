from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from src.domains.cli_workflow.models import CLIWorkflowMemory, ParameterBinding
from src.domains.cli_workflow.retriever import CLIWorkflowRetriever, CLIWorkflowSearchResult
from src.retrieval import MemoryItem, RetrievalQuery, memory_item_from_core
from src.storage.cli_workflow_store import CLIWorkflowStore
from src.storage.memory_core_store import MemoryCoreStore


class FakeKeywordLLM:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        return self.payload


@pytest.fixture
def temp_dir():
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    d = root / f"cli-workflow-retriever-{uuid.uuid4().hex}"
    d.mkdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def memory_store_with_data(temp_dir):
    db_path = str(temp_dir / "test_retriever.db")
    store = MemoryCoreStore(db_path)
    store.create_table()

    memories = [
        CLIWorkflowMemory(
            workflow_id="mem-shell-1",
            user_id="u_1",
            command_template="lark project deploy --env {env} --region {region}",
            command_name="lark project deploy",
            command_category="deploy",
            project_id="backend",
            parameter_bindings=[
                ParameterBinding(param_name="env", param_value="prod", frequency=42),
                ParameterBinding(param_name="region", param_value="cn-shanghai", frequency=42),
            ],
            execution_count=42,
            last_executed_at="2026-05-03T10:00:00Z",
            success_count=40,
        ),
        CLIWorkflowMemory(
            workflow_id="mem-shell-2",
            user_id="u_1",
            command_template="lark project build --target {target}",
            command_name="lark project build",
            command_category="build",
            project_id="backend",
            parameter_bindings=[
                ParameterBinding(param_name="target", param_value="release", frequency=15),
            ],
            execution_count=15,
            last_executed_at="2026-05-01T10:00:00Z",
            success_count=15,
        ),
        CLIWorkflowMemory(
            workflow_id="mem-shell-3",
            user_id="u_2",
            command_template="lark project deploy --env {env}",
            command_name="lark project deploy",
            command_category="deploy",
            project_id="frontend",
            parameter_bindings=[
                ParameterBinding(param_name="env", param_value="staging", frequency=5),
            ],
            execution_count=5,
            last_executed_at="2026-04-28T10:00:00Z",
            success_count=5,
        ),
    ]
    for m in memories:
        store.insert_memory_core(m.to_memory_core())

    return store


class TestCLIWorkflowRetriever:
    def test_retrieve_by_user(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="deploy", user_id="u_1")
        results = retriever.retrieve(query, limit=10)
        assert len(results) >= 1
        for r in results:
            assert r.memory.user_id == "u_1"

    def test_retrieve_by_user_and_project(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="deploy", user_id="u_1", project_id="backend")
        results = retriever.retrieve(query, limit=10)
        assert len(results) >= 1
        assert results[0].memory.project_id == "backend"

    def test_retrieve_other_user_sees_nothing(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="deploy", user_id="u_3")
        results = retriever.retrieve(query, limit=10)
        assert len(results) == 0

    def test_retrieve_by_command_name(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="build", user_id="u_1")
        results = retriever.retrieve(query, limit=10)
        assert len(results) >= 1
        assert results[0].memory.command_name == "lark project build"

    def test_retrieve_empty_query(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="", user_id="u_1")
        results = retriever.retrieve(query, limit=10)
        assert len(results) >= 1

    def test_retrieve_without_user_id_returns_empty(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="deploy")
        results = retriever.retrieve(query, limit=10)
        assert len(results) == 0

    def test_search_result_to_ranked_memory(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="deploy", user_id="u_1")
        results = retriever.retrieve(query, limit=10)
        if results:
            ranked = results[0].to_ranked_memory(rank=1)
            assert ranked.rank == 1
            assert ranked.final_score > 0
            assert "workflow" in ranked.item.extra

    def test_search_result_to_suggestion(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="deploy", user_id="u_1")
        results = retriever.retrieve(query, limit=10)
        if results:
            suggestion = results[0].to_suggestion()
            assert suggestion["command_name"] == "lark project deploy"
            assert len(suggestion["parameter_bindings"]) >= 1

    def test_search_result_to_completion(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="deploy", user_id="u_1")
        results = retriever.retrieve(query, limit=10)
        if results:
            completions = results[0].to_completion()
            assert len(completions) >= 1
            for comp in completions:
                assert comp.startswith("--")

    def test_higher_frequency_ranks_higher(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data)
        query = RetrievalQuery(query_text="lark project", user_id="u_1")
        results = retriever.retrieve(query, limit=10)
        assert len(results) >= 2
        assert results[0].score >= results[1].score

    def test_natural_language_query_does_not_filter_by_first_word(self, memory_store_with_data):
        memory = CLIWorkflowMemory(
            workflow_id="mem-pytest",
            user_id="u_1",
            command_template="pytest tests/test_cli.py -q",
            command_name="pytest tests/test_cli.py",
            command_category="test",
            project_id="backend",
            execution_count=3,
            success_count=3,
        )
        memory_store_with_data.insert_memory_core(memory.to_memory_core())
        retriever = CLIWorkflowRetriever(memory_store_with_data)

        results = retriever.retrieve(
            RetrievalQuery(query_text="最近常用的 CLI 测试命令", user_id="u_1", project_id="backend"),
            limit=10,
        )

        assert any(result.memory.workflow_id == "mem-pytest" for result in results)

    def test_prefix_query_ranks_matching_command_first(self, memory_store_with_data):
        memory = CLIWorkflowMemory(
            workflow_id="mem-python",
            user_id="u_1",
            command_template="python scripts/train.py --epochs {epochs}",
            command_name="python scripts/train.py",
            command_category="script",
            project_id="backend",
            parameter_bindings=[ParameterBinding(param_name="epochs", param_value="3")],
            execution_count=1,
            success_count=1,
        )
        memory_store_with_data.insert_memory_core(memory.to_memory_core())
        retriever = CLIWorkflowRetriever(memory_store_with_data)

        results = retriever.retrieve(
            RetrievalQuery(query_text="py 前缀补全", user_id="u_1", project_id="backend"),
            limit=10,
        )

        assert results[0].memory.workflow_id == "mem-python"

    def test_taught_command_pattern_ranks_above_observed_frequency(self, temp_dir):
        db_path = str(temp_dir / "test_taught_pattern.db")
        memory_store = MemoryCoreStore(db_path)
        memory_store.create_table()
        cli_store = CLIWorkflowStore(db_path)
        cli_store.create_table()

        observed = CLIWorkflowMemory(
            workflow_id="mem-observed",
            user_id="u_1",
            command_template="python scripts/deploy.py --env {env} --canary {canary}",
            command_name="python scripts/deploy.py",
            command_category="deploy",
            project_id="backend",
            parameter_bindings=[
                ParameterBinding(param_name="env", param_value="prod", frequency=80),
                ParameterBinding(param_name="canary", param_value="5", frequency=80),
            ],
            execution_count=80,
            success_count=80,
            source_type="shell",
        )
        taught = CLIWorkflowMemory(
            workflow_id="mem-taught",
            user_id="u_1",
            command_template="python scripts/release.py --tenant {tenant} --env {env} --canary {canary}",
            command_name="python scripts/release.py",
            command_category="deploy",
            project_id="backend",
            parameter_bindings=[
                ParameterBinding(param_name="tenant", param_value="demo-a", frequency=1),
                ParameterBinding(param_name="env", param_value="staging", frequency=1),
                ParameterBinding(param_name="canary", param_value="10", frequency=1),
            ],
            execution_count=1,
            success_count=1,
            source_type="openclaw",
        )
        memory_store.insert_memory_core(observed.to_memory_core())
        memory_store.insert_memory_core(taught.to_memory_core())
        cli_store.upsert_pattern(observed, memory_id_value=observed.workflow_id)
        cli_store.upsert_pattern(
            taught,
            memory_id_value=taught.workflow_id,
            semantic_description="部署 demo-a 租户使用 staging 环境和 10 灰度",
        )

        retriever = CLIWorkflowRetriever(memory_store, cli_store=cli_store)
        results = retriever.retrieve(
            RetrievalQuery(query_text="部署 demo-a 租户", user_id="u_1", project_id="backend"),
            limit=5,
        )

        assert results[0].memory.workflow_id == "mem-taught"
        assert "taught_command" in results[0].matched_fields

    def test_taught_parameter_policy_overrides_observed_binding(self, temp_dir):
        db_path = str(temp_dir / "test_taught_policy.db")
        memory_store = MemoryCoreStore(db_path)
        memory_store.create_table()
        cli_store = CLIWorkflowStore(db_path)
        cli_store.create_table()

        observed = CLIWorkflowMemory(
            workflow_id="mem-deploy",
            user_id="u_1",
            command_template="python scripts/deploy.py --env {env} --tenant {tenant}",
            command_name="python scripts/deploy.py",
            command_category="deploy",
            project_id="backend",
            parameter_bindings=[
                ParameterBinding(param_name="env", param_value="prod", frequency=60),
                ParameterBinding(param_name="tenant", param_value="demo-a", frequency=60),
            ],
            execution_count=60,
            success_count=60,
            source_type="shell",
        )
        memory_store.insert_memory_core(observed.to_memory_core())
        cli_store.upsert_pattern(observed, memory_id_value=observed.workflow_id)
        cli_store.upsert_parameter_policy(
            scenario_text="记住部署 demo-a 的时候参数 env 设置为 staging",
            semantic_description="部署 demo-a 的时候 env 使用 staging",
            param_name="env",
            param_value="staging",
            user_id="u_1",
            project_id="backend",
        )

        retriever = CLIWorkflowRetriever(memory_store, cli_store=cli_store)
        results = retriever.retrieve(
            RetrievalQuery(query_text="部署 demo-a", user_id="u_1", project_id="backend"),
            limit=5,
        )
        suggestion = results[0].to_suggestion()

        assert suggestion["parameter_bindings"][0]["param_name"] == "env"
        assert suggestion["parameter_bindings"][0]["param_value"] == "staging"
        assert "taught_param:env" in results[0].matched_fields

    def test_llm_keywords_drive_bm25_recall(self, temp_dir):
        db_path = str(temp_dir / "test_bm25_recall.db")
        memory_store = MemoryCoreStore(db_path)
        memory_store.create_table()
        unrelated = CLIWorkflowMemory(
            workflow_id="mem-noise",
            user_id="u_1",
            command_template="git status",
            command_name="git status",
            command_category="vcs",
            project_id="backend",
            execution_count=100,
            success_count=100,
        )
        target = CLIWorkflowMemory(
            workflow_id="mem-seed",
            user_id="u_1",
            command_template="python tools/seed.py --tenant {tenant} --dry-run",
            command_name="python tools/seed.py",
            command_category="script",
            project_id="backend",
            semantic_description="初始化 demo-a 租户的种子数据并使用 dry-run 预检查",
            scenario_keywords=["初始化", "种子数据", "dry-run"],
            parameter_bindings=[ParameterBinding(param_name="tenant", param_value="demo-a")],
            execution_count=1,
            success_count=1,
        )
        memory_store.insert_memory_core(unrelated.to_memory_core())
        memory_store.insert_memory_core(target.to_memory_core())
        llm = FakeKeywordLLM({
            "keywords": ["种子数据", "dry-run", "demo-a"],
            "semantic_query": "初始化 demo-a 租户种子数据 dry-run",
        })
        retriever = CLIWorkflowRetriever(memory_store, llm_client=llm)

        results = retriever.retrieve(
            RetrievalQuery(query_text="帮我做 demo-a 的初始化预检查", user_id="u_1", project_id="backend"),
            limit=5,
        )

        assert results[0].memory.workflow_id == "mem-seed"
        assert "bm25" in results[0].matched_fields

    def test_low_confidence_returns_empty(self, memory_store_with_data):
        retriever = CLIWorkflowRetriever(memory_store_with_data, min_relevance_score=2.0)

        results = retriever.retrieve(
            RetrievalQuery(query_text="完全无关的问题", user_id="u_1", project_id="backend"),
            limit=5,
        )

        assert results == []
