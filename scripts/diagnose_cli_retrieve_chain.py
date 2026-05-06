from __future__ import annotations

import argparse
import json
import os
import shlex
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


COMMAND_PREFIXES = {
    "git", "docker", "docker-compose", "kubectl", "k", "helm",
    "npm", "npx", "yarn", "pnpm", "bun", "node", "deno",
    "uv", "pip", "pip3", "python", "python3", "pytest", "poetry",
    "go", "cargo", "make", "cmake", "gradle", "mvn",
    "terraform", "tofu", "ansible", "lark", "lark-cli",
    "curl", "wget", "ssh", "scp", "rsync", "gh", "glab",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose CLI workflow retrieval from SQLite frequency table to retrieve API.",
    )
    parser.add_argument(
        "--query",
        default="git log 命令我最经常用的参数是什么",
        help="OpenClaw/API query text to test.",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("LARKMEMORY_SQLITE_PATH", ".larkmemory/larkmemory.db"),
        help="SQLite database path. Defaults to LARKMEMORY_SQLITE_PATH or .larkmemory/larkmemory.db.",
    )
    parser.add_argument("--api", default="http://127.0.0.1:8765", help="LarkMemory API base URL.")
    parser.add_argument("--user-id", default=None, help="Optional user_id sent to /api/v1/retrieve.")
    parser.add_argument("--project-id", default=None, help="Optional project_id sent to /api/v1/retrieve.")
    parser.add_argument("--base-command", default=None, help="Override parsed base command, e.g. git.")
    parser.add_argument("--sub-command", default=None, help="Override parsed sub command, e.g. 'git log'.")
    parser.add_argument("--top-k", type=int, default=5, help="API top_k.")
    return parser.parse_args()


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def parse_command_identity(query: str) -> tuple[str, str | None]:
    try:
        tokens = shlex.split(query, posix=False)
    except ValueError:
        tokens = query.split()
    cleaned_tokens: list[str] = []
    for token in tokens:
        cleaned = token.strip("\"'`“”‘’，,。？?：:")
        if not cleaned:
            continue
        if not cleaned_tokens:
            if cleaned.lower() not in COMMAND_PREFIXES:
                continue
            cleaned_tokens.append(cleaned)
            continue
        if cleaned.startswith("-"):
            break
        if any("\u4e00" <= ch <= "\u9fff" for ch in cleaned):
            break
        cleaned_tokens.append(cleaned)
        if cleaned_tokens[0].lower() in {"python", "python3", "node", "deno", "bun"}:
            break
        if len(cleaned_tokens) >= 3:
            break
    if not cleaned_tokens:
        return "", None
    if len(cleaned_tokens) == 1:
        return cleaned_tokens[0], None
    return cleaned_tokens[0], " ".join(cleaned_tokens[:2])


def normalize_command(value: str) -> str:
    return " ".join(value.replace("\\", "/").split()).lower()


def connect_db(db_path: str) -> sqlite3.Connection | None:
    path = Path(db_path)
    print("DB path:", path)
    print("DB exists:", path.exists())
    if not path.exists():
        return None
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def load_pattern_rows(
    con: sqlite3.Connection,
    *,
    base_command: str,
    sub_command: str | None,
) -> list[dict[str, Any]]:
    if not table_exists(con, "cli_command_pattern"):
        print("cli_command_pattern table: MISSING")
        return []
    rows = con.execute(
        """
        SELECT *
        FROM cli_command_pattern
        WHERE status='active'
          AND LOWER(base_command)=LOWER(?)
        ORDER BY execution_count DESC, updated_at DESC
        """,
        (base_command,),
    ).fetchall()
    result = [dict(row) for row in rows]
    if sub_command:
        expected = normalize_command(sub_command)
        result = [
            row for row in result
            if normalize_command(str(row.get("sub_command") or "")) == expected
        ]
    return result


def decode_bindings(row: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        value = json.loads(row.get("parameter_bindings_json") or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def print_pattern_rows(rows: list[dict[str, Any]]) -> None:
    print("matched cli_command_pattern rows:", len(rows))
    if not rows:
        return
    for index, row in enumerate(rows[:10], start=1):
        bindings = decode_bindings(row)
        print(f"\n[{index}] pattern_id={row.get('pattern_id')} memory_id={row.get('memory_id')}")
        print("user_id:", row.get("user_id"), "project_id:", row.get("project_id"))
        print("base:", row.get("base_command"))
        print("sub :", row.get("sub_command"))
        print("count:", row.get("execution_count"), "success:", row.get("success_count"), "rate:", row.get("success_rate"))
        print("template:", row.get("command_template"))
        print("params:", [
            {
                "name": item.get("param_name"),
                "value": item.get("param_value"),
                "frequency": item.get("frequency"),
            }
            for item in bindings
        ])


def expected_frequency_answer(rows: list[dict[str, Any]]) -> None:
    print_section("Expected Answer From Frequency Table")
    if not rows:
        print("No structured frequency row matched the parsed command identity.")
        return
    best = rows[0]
    bindings = sorted(
        decode_bindings(best),
        key=lambda item: -int(item.get("frequency") or 0),
    )
    print("command:", best.get("sub_command") or best.get("base_command"))
    print("execution_count:", best.get("execution_count"))
    if not bindings:
        print("No parameter bindings recorded for this command.")
        return
    for item in bindings[:10]:
        name = item.get("param_name")
        value = item.get("param_value")
        freq = item.get("frequency")
        print(f"--{name} {value} ({freq} times)")


def call_retrieve_api(
    *,
    api_base: str,
    query: str,
    user_id: str | None,
    project_id: str | None,
    top_k: int,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "query_text": query,
        "top_k": top_k,
        "include_trace": True,
    }
    if user_id:
        payload["user_id"] = user_id
    if project_id:
        payload["project_id"] = project_id
    url = api_base.rstrip("/") + "/api/v1/retrieve"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    print("POST", url)
    print("payload:", json.dumps(payload, ensure_ascii=False))
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print("API request failed:", repr(exc))
        return None


def print_api_result(response: dict[str, Any] | None, expected_sub_command: str | None) -> None:
    print_section("Retrieve API Result")
    if response is None:
        return
    trace = response.get("trace") or {}
    results = response.get("results") or []
    print("message:", response.get("message"))
    print("trace:", json.dumps(trace, ensure_ascii=False, indent=2))
    print("result_count:", len(results))
    for index, item in enumerate(results[:5], start=1):
        print(f"\n[{index}] memory_id={item.get('memory_id')} domain={item.get('domain')} score={item.get('score')}")
        print("summary:", item.get("summary_text"))
        entities = item.get("entities") or []
        print("entities:", entities[:6])
        content = str(item.get("content_text") or "")
        first_line = content.splitlines()[0] if content else ""
        print("content_first_line:", first_line)
    if trace.get("mode") != "domain_handlers":
        print("\nDIAGNOSIS: API did not return domain handler results.")
        print("It fell back to MemoryCore, so cli_command_pattern frequency retrieval was not used.")
    elif expected_sub_command:
        serialized = json.dumps(results, ensure_ascii=False).lower()
        if normalize_command(expected_sub_command) not in normalize_command(serialized):
            print("\nDIAGNOSIS: API used domain handlers, but returned result does not mention expected sub-command.")


def print_diagnosis(rows: list[dict[str, Any]], response: dict[str, Any] | None) -> None:
    print_section("Likely Broken Layer")
    if not rows:
        print("1. SQLite frequency table has no matching active row for the command identity.")
        print("   Check whether shell hook recorded this command and whether API points at the same DB.")
        return
    if response is None:
        print("1. Frequency table has data, but retrieve API is unreachable.")
        return
    trace = response.get("trace") or {}
    results = response.get("results") or []
    if trace.get("mode") == "memory_core_fallback":
        print("1. Frequency table has the expected row.")
        print("2. API returned memory_core_fallback, so domain handler retrieval produced 0 candidates.")
        print("3. Most likely causes:")
        print("   - query was not routed to cli_workflow;")
        print("   - cli_workflow handler used user/project filters that excluded the row;")
        print("   - API service is reading a different SQLite DB from the shell hook.")
        return
    if trace.get("mode") == "domain_handlers" and not results:
        print("1. API entered domain handler mode but returned no results.")
        print("2. Check base/sub-command parsing and project filters.")
        return
    if trace.get("mode") == "domain_handlers":
        print("1. API entered domain handler retrieval.")
        print("2. If the result is still wrong, inspect returned command identity and ranking.")
        return
    print("Trace mode is missing or unknown. Inspect raw trace above.")


def main() -> int:
    args = parse_args()
    print_section("Inputs")
    print("query:", args.query)
    print("python:", sys.executable)
    print("cwd:", os.getcwd())
    base_command, sub_command = parse_command_identity(args.query)
    if args.base_command:
        base_command = args.base_command
    if args.sub_command:
        sub_command = args.sub_command
    print("parsed base_command:", base_command or "<none>")
    print("parsed sub_command:", sub_command or "<none>")
    if not base_command:
        print("Could not parse a CLI command identity from query.")
        return 2

    print_section("SQLite Frequency Table")
    con = connect_db(args.db)
    if con is None:
        rows: list[dict[str, Any]] = []
    else:
        rows = load_pattern_rows(con, base_command=base_command, sub_command=sub_command)
        print_pattern_rows(rows)
        con.close()

    expected_frequency_answer(rows)
    response = call_retrieve_api(
        api_base=args.api,
        query=args.query,
        user_id=args.user_id,
        project_id=args.project_id,
        top_k=args.top_k,
    )
    print_api_result(response, sub_command)
    print_diagnosis(rows, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
