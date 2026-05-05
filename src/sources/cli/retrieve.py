from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from src.sources.cli._client import post_retrieve
from src.sources.cli.ingest import _detect_project_id, _detect_user_id


def _hit_to_workflow(hit: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a MemoryHit response dict to CLI workflow memory dict.

    The retrieve API returns MemoryHit which has content_text, tags, entities
    but no extra field. We use CLIWorkflowMemory.from_memory_core() to
    reconstruct domain data from those available fields.
    """
    from src.domains.cli_workflow.models import CLIWorkflowMemory

    if hit.get("domain") != "cli_workflow":
        return None
    try:
        wf = CLIWorkflowMemory.from_memory_core(hit)
        return wf.to_dict()
    except Exception:
        return None


def _hit_score(hit: dict[str, Any]) -> float:
    return float(hit.get("score", 0))


def _normalize_for_compare(value: str) -> str:
    """Normalize command identity strings for shell-facing comparisons."""
    return value.replace("\\", "/").lower().strip()


def _msys_to_windows_path(value: str) -> str:
    """Convert Git Bash style /c/... paths when running on Windows Python."""
    if len(value) >= 3 and value[0] == "/" and value[2] == "/":
        drive = value[1]
        if drive.isalpha():
            return f"{drive.upper()}:/{value[3:]}"
    return value


def _resolve_cli_path(value: str, *, cwd: str | None = None) -> str:
    """Resolve a command path relative to cwd for stable command matching."""
    normalized_cwd = _msys_to_windows_path(cwd or os.getcwd())
    normalized_value = _msys_to_windows_path(value)
    path = Path(normalized_value.replace("/", os.sep))
    if not path.is_absolute():
        path = Path(normalized_cwd.replace("/", os.sep)) / path
    try:
        return str(path.resolve())
    except OSError:
        return str(path.absolute())


def _query_command_identity(line: str, *, cwd: str | None = None) -> str:
    """Extract the command identity from a suggest query or completion line."""
    try:
        tokens = shlex.split(line.strip())
    except ValueError:
        tokens = line.strip().split()
    if not tokens:
        return ""
    executable = tokens[0]
    if (
        len(tokens) >= 2
        and executable.lower() in {"python", "python3", "node", "deno", "bun"}
        and _looks_like_script_path(tokens[1])
    ):
        return f"{executable} {_resolve_cli_path(tokens[1], cwd=cwd)}"
    identity = []
    for token in tokens:
        if token.startswith("--") or (token.startswith("-") and len(token) == 2):
            break
        if token.startswith("-"):
            break
        identity.append(token)
        if len(identity) >= 3:
            break
    return " ".join(identity)


def _looks_like_script_path(value: str) -> bool:
    lowered = value.lower()
    return (
        "/" in value
        or "\\" in value
        or lowered.endswith((".py", ".js", ".ts", ".mjs", ".cjs"))
    )


def _is_specific_script_identity(value: str) -> bool:
    """Return True for identities such as `python C:/repo/tool.py`."""
    first, sep, rest = value.partition(" ")
    return bool(
        sep
        and first.lower() in {"python", "python3", "node", "deno", "bun"}
        and _looks_like_script_path(rest)
    )


def _workflow_matches_command(wf: dict[str, Any], query: str, *, cwd: str | None = None) -> bool:
    """Return True when a workflow belongs to the command requested by the CLI."""
    command_name = str(wf.get("command_name") or "")
    if not command_name or not query.strip():
        return True
    query_identity = _query_command_identity(query, cwd=cwd)
    if not query_identity:
        return True
    command_cmp = _normalize_for_compare(command_name)
    query_cmp = _normalize_for_compare(query_identity)
    query_first = query_cmp.split(" ", 1)[0]
    command_first = command_cmp.split(" ", 1)[0]
    query_is_script = _is_specific_script_identity(query_cmp)
    command_is_script = _is_specific_script_identity(command_cmp)
    if query_is_script:
        return command_is_script and command_cmp == query_cmp
    if " " not in query_cmp:
        return command_first == query_first or query_cmp in command_cmp
    return command_cmp.startswith(query_cmp) or query_cmp.startswith(command_cmp)


def _filter_results_by_command(
    results: list[dict[str, Any]],
    query: str,
    *,
    cwd: str | None = None,
) -> list[dict[str, Any]]:
    """Filter MemoryHit rows to workflows matching the requested command."""
    filtered: list[dict[str, Any]] = []
    for result in results:
        wf = _hit_to_workflow(result)
        if wf is not None and _workflow_matches_command(wf, query, cwd=cwd):
            filtered.append(result)
    return filtered


def _format_suggest(results: list[dict[str, Any]]) -> str:
    if not results:
        return "未找到匹配的命令记忆。"

    workflows: list[dict[str, Any]] = []
    for result in results:
        wf = _hit_to_workflow(result)
        if wf:
            workflows.append(wf)
    if not workflows:
        return "未找到匹配的命令记忆。"

    # 按执行频率降序
    workflows.sort(key=lambda w: -(w.get("execution_count", 0)))

    lines: list[str] = []
    for i, wf in enumerate(workflows[:3]):
        count = wf.get("execution_count", 0)
        rate = wf.get("success_rate", 0)
        template = wf.get("command_template", wf.get("command_name", "?"))

        lines.append(f"\n  [{i+1}] {wf.get('command_name', '?')}  ({count}次, {rate:.0%}成功)")
        lines.append(f"  模板: {template}")

        bindings = wf.get("parameter_bindings") or []
        if bindings:
            top_bindings = sorted(bindings, key=lambda b: -b.get("frequency", 0))[:5]
            params = "  ".join(
                f"--{pb['param_name']} {pb['param_value']}"
                for pb in top_bindings
            )
            lines.append(f"  常用参数: {params}")

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
        results = post_retrieve(payload)
        results = _filter_results_by_command(results, command or query_text, cwd=cwd)
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
        "top_k": 10,
        "include_trace": False,
    }
    if actual_project:
        payload["project_id"] = actual_project

    try:
        results = post_retrieve(payload)
    except Exception:
        return ""
    results = _filter_results_by_command(results, line, cwd=cwd)
    if not results:
        return ""

    candidates: list[str] = []
    seen: set[str] = set()

    for result in results:
        wf = _hit_to_workflow(result)
        if not wf:
            continue
        for pb in sorted(
            wf.get("parameter_bindings") or [],
            key=lambda b: -b.get("frequency", 0),
        ):
            flag = f"--{pb['param_name']}"
            if flag not in seen and flag not in line:
                seen.add(flag)
                candidates.append(f"{flag} {pb.get('param_value', '')}")

    return "\n".join(candidates[:10])
