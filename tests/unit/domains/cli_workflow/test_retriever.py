from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from src.domains.cli_workflow.models import CLIWorkflowMemory, ParameterBinding
from src.domains.cli_workflow.retriever import CLIWorkflowRetriever, CLIWorkflowSearchResult
from src.retrieval import MemoryItem, RetrievalQuery, memory_item_from_core
from src.storage.memory_core_store import MemoryCoreStore


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
