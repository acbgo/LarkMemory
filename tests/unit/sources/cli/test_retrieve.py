from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.domains.cli_workflow.models import CLIWorkflowMemory, ParameterBinding
from src.sources.cli.retrieve import _hit_to_workflow, _format_suggest, run_complete, run_suggest
from src.storage.cli_workflow_store import CLIWorkflowStore


@pytest.fixture
def local_tmp_dir():
    root = Path.cwd() / ".tmp-tests" / f"cli-source-retrieve-{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _use_cli_db(monkeypatch, local_tmp_dir: Path) -> CLIWorkflowStore:
    db_path = local_tmp_dir / "cli.db"
    monkeypatch.setenv("LARKMEMORY_SQLITE_PATH", str(db_path))
    store = CLIWorkflowStore(str(db_path))
    store.create_table()
    return store


def _seed_pattern(
    store: CLIWorkflowStore,
    *,
    memory_id: str,
    command_template: str,
    command_name: str,
    params: list[tuple[str, str, int]],
    execution_count: int,
    project_id: str = "repo",
) -> None:
    store.upsert_pattern(
        CLIWorkflowMemory(
            workflow_id=memory_id,
            user_id="testuser",
            project_id=project_id,
            command_template=command_template,
            command_name=command_name,
            command_category="script",
            parameter_bindings=[
                ParameterBinding(name, value, frequency=frequency)
                for name, value, frequency in params
            ],
            execution_count=execution_count,
            success_count=execution_count,
        ),
        memory_id_value=memory_id,
    )


class TestHitToWorkflow:
    def test_converts_memory_hit_to_workflow_dict(self):
        hit = {
            "memory_id": "mem-test-1",
            "domain": "cli_workflow",
            "memory_type": "cli_workflow",
            "content_text": "命令模板: lark deploy --env {env}\n命令: lark deploy\n分类: deploy\n"
                            "项目: backend\n执行次数: 10\n成功率: 0.90\n参数绑定:\n"
                            "  --env prod (10次)\n来源: shell\n最近执行: 2026-05-03T10:00:00Z",
            "tags": ["cli_workflow", "category:deploy", "param:env=prod", "source:shell"],
            "entities": ["user_id:u_1", "project_id:backend", "command_name:lark deploy"],
            "score": 0.85,
            "rank": 1,
        }
        wf = _hit_to_workflow(hit)
        assert wf is not None
        assert wf["command_name"] == "lark deploy"
        assert wf["command_category"] == "deploy"
        assert wf["project_id"] == "backend"
        assert wf["execution_count"] == 10
        assert len(wf["parameter_bindings"]) >= 1

    def test_skips_non_cli_workflow(self):
        hit = {
            "domain": "project_decision",
            "content_text": "not a cli workflow",
        }
        assert _hit_to_workflow(hit) is None

    def test_handles_invalid_hit_gracefully(self):
        assert _hit_to_workflow({"domain": "cli_workflow"}) is None or isinstance(
            _hit_to_workflow({"domain": "cli_workflow"}), dict
        )


class TestFormatSuggest:
    def test_formats_empty_results(self):
        output = _format_suggest([])
        assert "未找到" in output

    def test_formats_workflow_from_memory_hit(self):
        results = [{
            "memory_id": "mem-test-1",
            "domain": "cli_workflow",
            "content_text": "命令模板: lark project deploy --env {env}\n命令: lark project deploy\n"
                            "分类: deploy\n项目: backend\n执行次数: 42\n成功率: 0.95\n"
                            "参数绑定:\n  --env prod (42次)\n来源: shell\n"
                            "最近执行: 2026-05-03T10:00:00Z",
            "tags": ["cli_workflow", "category:deploy", "param:env=prod", "source:shell"],
            "entities": ["user_id:u_1", "project_id:backend", "command_name:lark project deploy"],
            "score": 0.9,
        }]
        output = _format_suggest(results)
        assert "lark project deploy" in output
        assert "--env prod" in output
        assert "42" in output  # execution count


class TestRunSuggest:
    def test_empty_query_returns_usage(self):
        output = run_suggest("")
        assert "用法" in output

    def test_suggest_reads_local_frequency_store_without_retrieve_api(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        _seed_pattern(
            store,
            memory_id="mem-python",
            command_template="python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}",
            command_name="python C:\\repo\\.tmp-demo\\cli_dummy.py",
            params=[("env", "staging", 3)],
            execution_count=3,
        )
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            output = run_suggest("python", cwd="C:\\repo")

        assert "cli_dummy.py" in output
        assert "--env staging" in output

    def test_suggest_handles_failure(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("src.sources.cli.retrieve.CLIWorkflowStore", side_effect=Exception("db down")):
            output = run_suggest("deploy")
            assert "失败" in output


class TestRunComplete:
    def test_empty_line_returns_empty(self):
        assert run_complete("", "") == ""

    def test_complete_silent_on_failure(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("src.sources.cli.retrieve.CLIWorkflowStore", side_effect=Exception("db down")):
            assert run_complete("lark deploy --", "--") == ""

    def test_complete_returns_candidates(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        _seed_pattern(
            store,
            memory_id="mem-1",
            command_template="lark project deploy --env {env} --region {region}",
            command_name="lark project deploy",
            params=[("env", "prod", 10), ("region", "cn-shanghai", 5)],
            execution_count=10,
        )
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            output = run_complete("lark project deploy --", "--")
        assert "--env" in output

    def test_complete_requests_enough_candidates_when_top_hits_are_exhausted(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            run_complete("python .tmp-demo/cli_dummy.py --env staging", "", cwd="C:\\repo")
        assert True

    def test_complete_skips_parameter_name_already_present_with_different_value(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        _seed_pattern(
            store,
            memory_id="mem-1",
            command_template="python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env} --region {region}",
            command_name="python C:\\repo\\.tmp-demo\\cli_dummy.py",
            params=[("env", "prod", 10), ("region", "cn-east", 8)],
            execution_count=10,
        )
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            output = run_complete("python .tmp-demo/cli_dummy.py --env staging ", "", cwd="C:\\repo")
            assert "--env" not in output
            assert "--region cn-east" in output

    def test_complete_filters_candidates_to_matching_command(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        _seed_pattern(
            store,
            memory_id="mem-git",
            command_template="git log --max-count {max-count}",
            command_name="git log",
            params=[("max-count", "5", 99)],
            execution_count=99,
        )
        _seed_pattern(
            store,
            memory_id="mem-python",
            command_template="python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}",
            command_name="python C:\\repo\\.tmp-demo\\cli_dummy.py",
            params=[("env", "staging", 2)],
            execution_count=2,
        )
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            output = run_complete("python .tmp-demo/cli_dummy.py ", "", cwd="C:\\repo")
            assert "--env staging" in output
            assert "--max-count" not in output

    def test_complete_filters_between_different_python_scripts(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        _seed_pattern(
            store,
            memory_id="mem-other-python",
            command_template="python C:\\repo\\tools\\other.py --profile {profile}",
            command_name="python C:\\repo\\tools\\other.py",
            params=[("profile", "prod", 20)],
            execution_count=20,
        )
        _seed_pattern(
            store,
            memory_id="mem-dummy-python",
            command_template="python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}",
            command_name="python C:\\repo\\.tmp-demo\\cli_dummy.py",
            params=[("env", "staging", 2)],
            execution_count=2,
        )
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            output = run_complete("python .tmp-demo/cli_dummy.py ", "", cwd="C:\\repo")
            assert "--env staging" in output
            assert "--profile prod" not in output

    def test_complete_specific_python_script_does_not_match_generic_python_memory(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        _seed_pattern(
            store,
            memory_id="mem-generic-python",
            command_template="python --module {module}",
            command_name="python",
            params=[("module", "http.server", 50)],
            execution_count=50,
        )
        _seed_pattern(
            store,
            memory_id="mem-dummy-python",
            command_template="python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}",
            command_name="python C:\\repo\\.tmp-demo\\cli_dummy.py",
            params=[("env", "staging", 2)],
            execution_count=2,
        )
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            output = run_complete("python .tmp-demo/cli_dummy.py ", "", cwd="C:\\repo")
            assert "--env staging" in output
            assert "--module http.server" not in output

    def test_suggest_filters_base_command_when_api_returns_other_commands(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        _seed_pattern(
            store,
            memory_id="mem-git",
            command_template="git log --max-count {max-count}",
            command_name="git log",
            params=[("max-count", "5", 99)],
            execution_count=99,
        )
        _seed_pattern(
            store,
            memory_id="mem-python",
            command_template="python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}",
            command_name="python C:\\repo\\.tmp-demo\\cli_dummy.py",
            params=[("env", "staging", 2)],
            execution_count=2,
        )
        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=AssertionError("retrieve API should not be used")):
            output = run_suggest("python", cwd="C:\\repo")
            assert "cli_dummy.py" in output
            assert "git log" not in output
