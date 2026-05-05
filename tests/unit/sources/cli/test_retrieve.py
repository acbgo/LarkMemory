from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from src.sources.cli.retrieve import _hit_to_workflow, _format_suggest, run_complete, run_suggest


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

    def test_suggest_calls_api(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"results": []}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            output = run_suggest("deploy")
            assert "未找到" in output

    def test_suggest_handles_failure(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            output = run_suggest("deploy")
            assert "失败" in output


class TestRunComplete:
    def test_empty_line_returns_empty(self):
        assert run_complete("", "") == ""

    def test_complete_silent_on_failure(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            assert run_complete("lark deploy --", "--") == ""

    def test_complete_returns_candidates(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "results": [{
                "memory_id": "mem-1",
                "domain": "cli_workflow",
                "content_text": "命令模板: lark project deploy --env {env}\n命令: lark project deploy\n"
                                "分类: deploy\n执行次数: 10\n成功率: 1.00\n"
                                "参数绑定:\n  --env prod (10次)\n  --region cn-shanghai (5次)\n来源: shell",
                "tags": ["cli_workflow", "param:env=prod", "param:region=cn-shanghai", "source:shell"],
                "entities": ["user_id:u_1", "command_name:lark project deploy"],
                "score": 0.9,
            }]
        }).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            output = run_complete("lark project deploy --", "--")
            assert "--env" in output

    def test_complete_requests_enough_candidates_when_top_hits_are_exhausted(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        captured = {}

        def fake_post_retrieve(payload):
            captured.update(payload)
            return []

        with patch("src.sources.cli.retrieve.post_retrieve", side_effect=fake_post_retrieve):
            run_complete("python .tmp-demo/cli_dummy.py --env staging", "", cwd="C:\\repo")

        assert captured["top_k"] >= 10

    def test_complete_skips_parameter_name_already_present_with_different_value(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        results = [{
            "memory_id": "mem-1",
            "domain": "cli_workflow",
            "content_text": "命令模板: python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env} --region {region}\n"
                            "命令: python C:\\repo\\.tmp-demo\\cli_dummy.py\n分类: script\n"
                            "执行次数: 10\n成功率: 1.00\n"
                            "参数绑定:\n  --env prod (10次)\n  --region cn-east (8次)\n来源: shell",
            "tags": ["cli_workflow", "param:env=prod", "param:region=cn-east", "source:shell"],
            "entities": ["user_id:testuser", "command_name:python C:\\repo\\.tmp-demo\\cli_dummy.py"],
            "score": 0.9,
        }]
        with patch("src.sources.cli.retrieve.post_retrieve", return_value=results):
            output = run_complete("python .tmp-demo/cli_dummy.py --env staging ", "", cwd="C:\\repo")
            assert "--env" not in output
            assert "--region cn-east" in output

    def test_complete_filters_candidates_to_matching_command(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        results = [
            {
                "memory_id": "mem-git",
                "domain": "cli_workflow",
                "content_text": "命令模板: git log --max-count {max-count}\n命令: git log\n"
                                "分类: vcs\n执行次数: 99\n成功率: 1.00\n"
                                "参数绑定:\n  --max-count 5 (99次)\n来源: shell",
                "tags": ["cli_workflow", "param:max-count=5", "source:shell"],
                "entities": ["user_id:testuser", "command_name:git log"],
                "score": 0.99,
            },
            {
                "memory_id": "mem-python",
                "domain": "cli_workflow",
                "content_text": "命令模板: python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}\n"
                                "命令: python C:\\repo\\.tmp-demo\\cli_dummy.py\n分类: script\n"
                                "执行次数: 2\n成功率: 1.00\n参数绑定:\n  --env staging (2次)\n来源: shell",
                "tags": ["cli_workflow", "param:env=staging", "source:shell"],
                "entities": ["user_id:testuser", "command_name:python C:\\repo\\.tmp-demo\\cli_dummy.py"],
                "score": 0.5,
            },
        ]
        with patch("src.sources.cli.retrieve.post_retrieve", return_value=results):
            output = run_complete("python .tmp-demo/cli_dummy.py ", "", cwd="C:\\repo")
            assert "--env staging" in output
            assert "--max-count" not in output

    def test_complete_filters_between_different_python_scripts(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        results = [
            {
                "memory_id": "mem-other-python",
                "domain": "cli_workflow",
                "content_text": "命令模板: python C:\\repo\\tools\\other.py --profile {profile}\n"
                                "命令: python C:\\repo\\tools\\other.py\n分类: script\n"
                                "执行次数: 20\n成功率: 1.00\n参数绑定:\n  --profile prod (20次)\n来源: shell",
                "tags": ["cli_workflow", "param:profile=prod", "source:shell"],
                "entities": ["user_id:testuser", "command_name:python C:\\repo\\tools\\other.py"],
                "score": 0.99,
            },
            {
                "memory_id": "mem-dummy-python",
                "domain": "cli_workflow",
                "content_text": "命令模板: python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}\n"
                                "命令: python C:\\repo\\.tmp-demo\\cli_dummy.py\n分类: script\n"
                                "执行次数: 2\n成功率: 1.00\n参数绑定:\n  --env staging (2次)\n来源: shell",
                "tags": ["cli_workflow", "param:env=staging", "source:shell"],
                "entities": ["user_id:testuser", "command_name:python C:\\repo\\.tmp-demo\\cli_dummy.py"],
                "score": 0.5,
            },
        ]
        with patch("src.sources.cli.retrieve.post_retrieve", return_value=results):
            output = run_complete("python .tmp-demo/cli_dummy.py ", "", cwd="C:\\repo")
            assert "--env staging" in output
            assert "--profile prod" not in output

    def test_complete_specific_python_script_does_not_match_generic_python_memory(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        results = [
            {
                "memory_id": "mem-generic-python",
                "domain": "cli_workflow",
                "content_text": "命令模板: python --module {module}\n命令: python\n"
                                "分类: script\n执行次数: 50\n成功率: 1.00\n"
                                "参数绑定:\n  --module http.server (50次)\n来源: shell",
                "tags": ["cli_workflow", "param:module=http.server", "source:shell"],
                "entities": ["user_id:testuser", "command_name:python"],
                "score": 0.99,
            },
            {
                "memory_id": "mem-dummy-python",
                "domain": "cli_workflow",
                "content_text": "命令模板: python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}\n"
                                "命令: python C:\\repo\\.tmp-demo\\cli_dummy.py\n分类: script\n"
                                "执行次数: 2\n成功率: 1.00\n参数绑定:\n  --env staging (2次)\n来源: shell",
                "tags": ["cli_workflow", "param:env=staging", "source:shell"],
                "entities": ["user_id:testuser", "command_name:python C:\\repo\\.tmp-demo\\cli_dummy.py"],
                "score": 0.5,
            },
        ]
        with patch("src.sources.cli.retrieve.post_retrieve", return_value=results):
            output = run_complete("python .tmp-demo/cli_dummy.py ", "", cwd="C:\\repo")
            assert "--env staging" in output
            assert "--module http.server" not in output

    def test_suggest_filters_base_command_when_api_returns_other_commands(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        results = [
            {
                "memory_id": "mem-git",
                "domain": "cli_workflow",
                "content_text": "命令模板: git log --max-count {max-count}\n命令: git log\n"
                                "分类: vcs\n执行次数: 99\n成功率: 1.00\n"
                                "参数绑定:\n  --max-count 5 (99次)\n来源: shell",
                "tags": ["cli_workflow", "param:max-count=5", "source:shell"],
                "entities": ["user_id:testuser", "command_name:git log"],
                "score": 0.99,
            },
            {
                "memory_id": "mem-python",
                "domain": "cli_workflow",
                "content_text": "命令模板: python C:\\repo\\.tmp-demo\\cli_dummy.py --env {env}\n"
                                "命令: python C:\\repo\\.tmp-demo\\cli_dummy.py\n分类: script\n"
                                "执行次数: 2\n成功率: 1.00\n参数绑定:\n  --env staging (2次)\n来源: shell",
                "tags": ["cli_workflow", "param:env=staging", "source:shell"],
                "entities": ["user_id:testuser", "command_name:python C:\\repo\\.tmp-demo\\cli_dummy.py"],
                "score": 0.5,
            },
        ]
        with patch("src.sources.cli.retrieve.post_retrieve", return_value=results):
            output = run_suggest("python", cwd="C:\\repo")
            assert "cli_dummy.py" in output
            assert "git log" not in output
