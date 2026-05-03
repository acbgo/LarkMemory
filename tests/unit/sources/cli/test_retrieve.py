from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from src.sources.cli.retrieve import _extract_workflow, _format_suggest, run_complete, run_suggest


class TestExtractWorkflow:
    def test_extracts_from_item_extra(self):
        memory = {
            "item": {
                "extra": {
                    "workflow": {
                        "command_name": "lark deploy",
                        "command_template": "lark deploy --env {env}",
                    }
                }
            }
        }
        wf = _extract_workflow(memory)
        assert wf is not None
        assert wf["command_name"] == "lark deploy"

    def test_extracts_from_top_level_extra(self):
        memory = {
            "extra": {
                "workflow": {
                    "command_name": "git push",
                }
            }
        }
        wf = _extract_workflow(memory)
        assert wf is not None
        assert wf["command_name"] == "git push"

    def test_returns_none_for_empty(self):
        assert _extract_workflow({}) is None


class TestFormatSuggest:
    def test_formats_empty_results(self):
        output = _format_suggest([])
        assert "未找到" in output

    def test_formats_single_result(self):
        results = [{
            "item": {
                "extra": {
                    "workflow": {
                        "command_name": "lark project deploy",
                        "command_category": "deploy",
                        "project_id": "backend",
                        "command_template": "lark project deploy --env {env}",
                        "parameter_bindings": [
                            {"param_name": "env", "param_value": "prod", "frequency": 42},
                        ],
                        "execution_count": 42,
                        "last_executed_at": "2026-05-03T10:00:00Z",
                        "success_rate": 0.95,
                    }
                }
            }
        }]
        output = _format_suggest(results)
        assert "lark project deploy" in output
        assert "backend" in output
        assert "env" in output
        assert "prod" in output
        assert "42" in output


class TestRunSuggest:
    def test_empty_query_returns_usage(self):
        output = run_suggest("")
        assert "用法" in output

    def test_suggest_sends_retrieve_request(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ranked_memories": []
        }).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            run_suggest("deploy")
            mock_urlopen.assert_called_once()

    def test_suggest_handles_request_failure(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            output = run_suggest("deploy")
            assert "失败" in output or "查询失败" in output


class TestRunComplete:
    def test_empty_line_returns_empty(self):
        output = run_complete("", "")
        assert output == ""

    def test_complete_returns_empty_on_failure(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            output = run_complete("lark deploy --", "--")
            assert output == ""

    def test_complete_returns_candidates(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ranked_memories": [{
                "item": {
                    "extra": {
                        "workflow": {
                            "command_name": "lark project deploy",
                            "command_template": "lark project deploy --env {env}",
                            "parameter_bindings": [
                                {"param_name": "env", "param_value": "prod", "frequency": 10},
                                {"param_name": "region", "param_value": "cn-shanghai", "frequency": 5},
                            ],
                        }
                    }
                }
            }]
        }).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            output = run_complete("lark project deploy --", "--")
            assert "--env" in output
