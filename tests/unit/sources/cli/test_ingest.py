from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from src.sources.cli.ingest import build_event, run_from_args


class TestBuildEvent:
    def test_successful_command(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        event = build_event(
            "lark project deploy --env prod",
            exit_code=0,
            cwd="/home/testuser/projects/backend",
            duration_ms=1200,
        )
        assert event["event_type"] == "command_finished"
        assert event["source_type"] == "shell"
        assert event["context"]["user_id"] == "testuser"
        assert event["context"]["scope"] == "user"
        assert event["content_text"] == "lark project deploy --env prod"
        assert event["payload"]["command"] == "lark"
        assert event["payload"]["args"] == ["project", "deploy", "--env", "prod"]
        assert event["payload"]["exit_code"] == 0
        assert event["payload"]["cwd"] == "/home/testuser/projects/backend"
        assert event["payload"]["duration_ms"] == 1200

    def test_failed_command(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        event = build_event(
            "lark project deploy --env prod",
            exit_code=1,
            cwd="/tmp",
        )
        assert event["event_type"] == "command_failed"

    def test_user_from_env(self, monkeypatch):
        monkeypatch.setenv("USER", "developer")
        event = build_event("git push")
        assert event["context"]["user_id"] == "developer"

    def test_user_fallback_to_unknown(self, monkeypatch):
        monkeypatch.delenv("USER", raising=False)
        monkeypatch.delenv("USERNAME", raising=False)
        with patch("subprocess.check_output", side_effect=Exception("no whoami")):
            event = build_event("git push")
            assert event["context"]["user_id"] == "unknown"

    def test_event_has_valid_event_id(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        event = build_event("git push")
        assert event["event_id"].startswith("evt-")
        assert len(event["event_id"]) > 10

    def test_payload_has_command_and_args(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        event = build_event("git push origin main")
        assert event["payload"]["command"] == "git"
        assert event["payload"]["args"] == ["push", "origin", "main"]

    def test_event_has_occurred_at(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        event = build_event("git push")
        assert "T" in event["occurred_at"]


class TestRunFromArgs:
    def test_skips_empty_command(self):
        result = run_from_args({"command": "", "exit_code": 0, "cwd": "/tmp", "duration": 100})
        assert result is False

    def test_skips_whitespace_command(self):
        result = run_from_args({"command": "   ", "exit_code": 0, "cwd": "/tmp", "duration": 100})
        assert result is False

    def test_sends_valid_command(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_urlopen.return_value = mock_resp
            result = run_from_args({
                "command": "git push",
                "exit_code": 0,
                "cwd": "/tmp",
                "duration": 100,
            })
            assert result is True
            mock_urlopen.assert_called_once()

    def test_silent_on_http_failure(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = run_from_args({
                "command": "git push",
                "exit_code": 0,
                "cwd": "/tmp",
                "duration": 100,
            })
            assert result is False
