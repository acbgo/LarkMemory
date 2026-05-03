from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from src.utils.ids import event_id as new_event_id
from src.utils.time import utc_now_iso


def _get_api_base() -> str:
    return os.environ.get("LARKMEMORY_API_BASE", "http://127.0.0.1:8765")


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
            "exit_code": exit_code,
            "cwd": cwd,
            "duration_ms": duration_ms,
        },
    }


def send_event(event: dict[str, Any]) -> bool:
    try:
        url = f"{_get_api_base().rstrip('/')}/api/v1/ingest"
        data = json.dumps(event, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


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
    return send_event(event)
