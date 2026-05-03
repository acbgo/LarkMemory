from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from src.sources.cli._client import post_ingest
from src.utils.ids import event_id as new_event_id
from src.utils.time import utc_now_iso


def _parse_command_tokens(command_text: str) -> tuple[str, list[str]]:
    try:
        tokens = shlex.split(command_text)
    except ValueError:
        tokens = command_text.split()
    if not tokens:
        return "", []
    return tokens[0], tokens[1:]


def _detect_user_id() -> str:
    user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    if not user:
        try:
            user = subprocess.check_output(
                ["whoami"], text=True, timeout=2
            ).strip()
        except Exception:
            user = "unknown"
    return user


def _detect_project_id(cwd: str) -> str | None:
    try:
        result = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd or None,
            text=True,
            timeout=3,
            stderr=subprocess.DEVNULL,
        ).strip()
        return Path(result).name
    except Exception:
        pass
    if cwd:
        return Path(cwd).name
    return None


def _detect_repo_id(cwd: str) -> str | None:
    try:
        result = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd or None,
            text=True,
            timeout=3,
            stderr=subprocess.DEVNULL,
        ).strip()
        return result
    except Exception:
        return None


def build_event(
    command: str,
    *,
    exit_code: int = 0,
    cwd: str = "",
    duration_ms: int = 0,
) -> dict[str, Any]:
    success = exit_code == 0
    cmd_name, cmd_args = _parse_command_tokens(command)
    return {
        "event_id": new_event_id(),
        "event_type": "command_failed" if not success else "command_finished",
        "source_type": "shell",
        "occurred_at": utc_now_iso(),
        "context": {
            "user_id": _detect_user_id(),
            "project_id": _detect_project_id(cwd),
            "repo_id": _detect_repo_id(cwd),
            "scope": "user",
        },
        "content_text": command,
        "payload": {
            "command": cmd_name,
            "args": cmd_args,
            "exit_code": exit_code,
            "cwd": cwd,
            "duration_ms": duration_ms,
        },
    }


def run_from_args(args: dict[str, Any]) -> bool:
    command = str(args.get("command") or "")
    if not command.strip():
        return False
    event = build_event(
        command,
        exit_code=int(args.get("exit_code", 0)),
        cwd=str(args.get("cwd", "")),
        duration_ms=int(args.get("duration", 0)),
    )
    try:
        post_ingest(event)
        return True
    except Exception:
        return False
