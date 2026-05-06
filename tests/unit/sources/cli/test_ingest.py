from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from src.sources.cli.ingest import build_event, run_from_args
from src.storage.cli_workflow_store import CLIWorkflowStore


@pytest.fixture
def local_tmp_dir():
    root = Path.cwd() / ".tmp-tests" / f"cli-source-ingest-{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _use_cli_db(monkeypatch, local_tmp_dir: Path) -> CLIWorkflowStore:
    db_path = local_tmp_dir / "cli.db"
    monkeypatch.setenv("LARKMEMORY_SQLITE_PATH", str(db_path))
    store = CLIWorkflowStore(str(db_path))
    store.create_table()
    return store


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

    def test_writes_valid_command_to_local_frequency_store(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        with patch("urllib.request.urlopen", side_effect=AssertionError("ingest API should not be used")):
            result = run_from_args({
                "command": "git push origin main",
                "exit_code": 0,
                "cwd": str(local_tmp_dir),
                "duration": 100,
            })
        assert result is True
        rows = store.list_patterns(user_id="testuser")
        assert len(rows) == 1
        assert rows[0]["base_command"] == "git"
        assert rows[0]["sub_command"] == "git push"
        assert rows[0]["execution_count"] == 1

    def test_accumulates_frequency_in_local_store(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        args = {
            "command": "python .tmp-demo/cli_dummy.py --env staging --tenant demo-a",
            "exit_code": 0,
            "cwd": str(local_tmp_dir),
            "duration": 100,
        }

        assert run_from_args(args) is True
        assert run_from_args(args) is True

        rows = store.list_patterns(user_id="testuser")
        assert len(rows) == 1
        assert rows[0]["execution_count"] == 2
        assert rows[0]["success_count"] == 2
        assert rows[0]["parameter_bindings"][0]["param_name"] == "env"

    def test_skips_trivial_command_without_http(self, monkeypatch, local_tmp_dir):
        monkeypatch.setenv("USER", "testuser")
        store = _use_cli_db(monkeypatch, local_tmp_dir)
        with patch("urllib.request.urlopen", side_effect=AssertionError("ingest API should not be used")):
            result = run_from_args({
                "command": "ls -la",
                "exit_code": 0,
                "cwd": str(local_tmp_dir),
                "duration": 100,
            })

        assert result is False
        assert store.list_patterns(user_id="testuser") == []
