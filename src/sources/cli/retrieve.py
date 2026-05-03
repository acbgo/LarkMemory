from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any

from src.sources.cli.ingest import _detect_project_id, _detect_user_id


def _get_api_base() -> str:
    return os.environ.get("LARKMEMORY_API_BASE", "http://127.0.0.1:8765")


def _post_retrieve(payload: dict[str, Any]) -> list[dict[str, Any]]:
    url = f"{_get_api_base().rstrip('/')}/api/v1/retrieve"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=5)
    body = json.loads(resp.read().decode("utf-8"))
    return body.get("results") or body.get("ranked_memories") or []


def _extract_workflow(memory: dict[str, Any]) -> dict[str, Any] | None:
    item = memory.get("item") or memory
    extra = item.get("extra", {}) if isinstance(item, dict) else {}
    return extra.get("workflow")


def _format_suggest(results: list[dict[str, Any]]) -> str:
    if not results:
        return "未找到匹配的命令记忆。"

    lines: list[str] = []
    for i, result in enumerate(results):
        wf = _extract_workflow(result)
        if not wf:
            continue
        lines.append("")
        lines.append(f"  [{i+1}] {wf.get('command_name', '?')}")
        lines.append(f"  分类: {wf.get('command_category', 'general')}")
        if wf.get("project_id"):
            lines.append(f"  项目: {wf['project_id']}")
        lines.append(f"  模板: {wf.get('command_template', '?')}")

        bindings = wf.get("parameter_bindings") or []
        if bindings:
            lines.append("  常用参数:")
            for pb in sorted(bindings, key=lambda b: -b.get("frequency", 0)):
                lines.append(
                    f"    --{pb['param_name']} {pb['param_value']}"
                    f"  ({pb.get('frequency', 0)}次)"
                )

        count = wf.get("execution_count", 0)
        last = wf.get("last_executed_at", "?")
        rate = wf.get("success_rate", 0)
        lines.append(f"  执行: {count}次 | 成功率: {rate:.0%} | 最近: {last}")
    return "\n".join(lines)


def run_suggest(
    query_text: str,
    *,
    project_id: str | None = None,
    command: str | None = None,
    cwd: str | None = None,
) -> str:
    if not query_text.strip():
        return "用法: lark-memory suggest <查询文本> [--project <项目>] [--command <命令>]"

    actual_project = project_id or _detect_project_id(cwd or os.getcwd())
    user_id = _detect_user_id()

    payload: dict[str, Any] = {
        "query_text": query_text,
        "user_id": user_id,
        "top_k": 10,
        "include_trace": False,
    }
    if actual_project:
        payload["project_id"] = actual_project

    try:
        results = _post_retrieve(payload)
        if command:
            results = [
                r for r in results
                if command.lower() in str(
                    (_extract_workflow(r) or {}).get("command_name", "")
                ).lower()
            ]
        return _format_suggest(results)
    except Exception as e:
        return f"查询失败: {e}"


def run_complete(line: str, cur: str, *, cwd: str | None = None) -> str:
    if not line.strip():
        return ""

    user_id = _detect_user_id()
    actual_project = _detect_project_id(cwd or os.getcwd())

    payload: dict[str, Any] = {
        "query_text": line,
        "user_id": user_id,
        "top_k": 3,
        "include_trace": False,
    }
    if actual_project:
        payload["project_id"] = actual_project

    try:
        results = _post_retrieve(payload)
    except Exception:
        return ""

    candidates: list[str] = []
    seen: set[str] = set()

    for result in results:
        wf = _extract_workflow(result)
        if not wf:
            continue
        for pb in sorted(
            wf.get("parameter_bindings") or [],
            key=lambda b: -b.get("frequency", 0),
        ):
            flag = f"--{pb['param_name']}"
            if flag not in seen:
                # Only suggest if the flag is not already on the command line
                if flag not in line:
                    seen.add(flag)
                    candidates.append(f"{flag} {pb.get('param_value', '')}")

    return "\n".join(candidates[:10])
