from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

from src.domains.cli_workflow.models import CLIWorkflowMemory, ParameterBinding
from src.utils.ids import memory_id
from src.utils.text import clean_text
from src.utils.time import utc_now_iso

from .base import SQLiteStore


class CLIWorkflowStore(SQLiteStore):
    """Structured persistence for CLI command patterns and taught parameter policies."""

    def create_table(self) -> None:
        """Create command pattern and parameter policy tables."""
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS cli_command_pattern (
                pattern_id TEXT PRIMARY KEY,
                memory_id TEXT,
                user_id TEXT NOT NULL,
                project_id TEXT,
                base_command TEXT NOT NULL,
                sub_command TEXT NOT NULL,
                full_command TEXT NOT NULL,
                normalized_full_command TEXT NOT NULL,
                command_template TEXT NOT NULL,
                cwd TEXT,
                normalized_cwd TEXT,
                semantic_description TEXT,
                source_type TEXT NOT NULL,
                memory_origin TEXT NOT NULL,
                active_priority REAL NOT NULL,
                execution_count INTEGER NOT NULL,
                success_count INTEGER NOT NULL,
                success_rate REAL NOT NULL,
                parameter_bindings_json TEXT NOT NULL,
                status TEXT NOT NULL,
                last_executed_at TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS cli_parameter_policy (
                policy_id TEXT PRIMARY KEY,
                memory_id TEXT,
                user_id TEXT NOT NULL,
                project_id TEXT,
                scenario_text TEXT NOT NULL,
                scenario_signature TEXT,
                semantic_description TEXT,
                target_base_command TEXT,
                target_sub_command TEXT,
                target_pattern_id TEXT,
                param_name TEXT NOT NULL,
                param_value TEXT NOT NULL,
                source_type TEXT NOT NULL,
                memory_origin TEXT NOT NULL,
                active_priority REAL NOT NULL,
                binding_status TEXT NOT NULL,
                status TEXT NOT NULL,
                overwrite_of TEXT,
                superseded_by TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cli_pattern_lookup
            ON cli_command_pattern (user_id, project_id, sub_command, status)
            """
        )
        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cli_pattern_origin
            ON cli_command_pattern (memory_origin, active_priority, status)
            """
        )
        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cli_policy_lookup
            ON cli_parameter_policy (user_id, project_id, param_name, status)
            """
        )
        self._ensure_column("cli_parameter_policy", "scenario_signature", "TEXT")

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        """Add a nullable column for existing SQLite databases when schema evolves."""
        columns = self.fetch_all(f"PRAGMA table_info({table})")
        if any(row["name"] == column for row in columns):
            return
        self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def upsert_pattern(
        self,
        memory: CLIWorkflowMemory,
        *,
        memory_id_value: str | None = None,
        cwd: str | None = None,
        semantic_description: str | None = None,
    ) -> str:
        """Insert or strengthen a command pattern row from a CLI workflow memory."""
        full_command = render_command(memory.command_template, memory.parameter_bindings)
        base_command, sub_command = split_command_identity(full_command)
        normalized_full = normalize_command_text(full_command)
        normalized_cwd = normalize_path(cwd or "")
        source_type = memory.source_type or "shell"
        origin = "taught_command" if source_type == "openclaw" else "observed"
        priority = 1.0 if origin == "taught_command" else 0.5
        now = utc_now_iso()
        existing = self.fetch_one(
            """
            SELECT * FROM cli_command_pattern
            WHERE user_id = ?
              AND COALESCE(project_id, '') = COALESCE(?, '')
              AND normalized_full_command = ?
              AND source_type = ?
              AND status = 'active'
            LIMIT 1
            """,
            (memory.user_id, memory.project_id, normalized_full, source_type),
        )
        bindings_json = json.dumps(
            [
                {
                    "param_name": binding.param_name,
                    "param_value": binding.param_value,
                    "frequency": binding.frequency,
                    "semantics": binding.semantics,
                }
                for binding in memory.parameter_bindings
            ],
            ensure_ascii=True,
        )
        if existing:
            execution_count = int(existing["execution_count"] or 0) + max(memory.execution_count, 1)
            success_count = int(existing["success_count"] or 0) + max(memory.success_count, 0)
            success_rate = success_count / execution_count if execution_count else 0.0
            self.execute(
                """
                UPDATE cli_command_pattern
                SET execution_count = ?,
                    success_count = ?,
                    success_rate = ?,
                    parameter_bindings_json = ?,
                    last_executed_at = ?,
                    updated_at = ?,
                    memory_id = COALESCE(?, memory_id),
                    semantic_description = COALESCE(?, semantic_description)
                WHERE pattern_id = ?
                """,
                (
                    execution_count,
                    success_count,
                    success_rate,
                    bindings_json,
                    memory.last_executed_at,
                    now,
                    memory_id_value,
                    semantic_description,
                    existing["pattern_id"],
                ),
            )
            return str(existing["pattern_id"])

        pattern_id = memory.workflow_id or memory_id()
        execution_count = max(memory.execution_count, 1)
        success_count = max(memory.success_count, 0)
        success_rate = success_count / execution_count if execution_count else 0.0
        self.execute(
            """
            INSERT INTO cli_command_pattern (
                pattern_id, memory_id, user_id, project_id, base_command, sub_command,
                full_command, normalized_full_command, command_template, cwd, normalized_cwd,
                semantic_description, source_type, memory_origin, active_priority,
                execution_count, success_count, success_rate, parameter_bindings_json,
                status, last_executed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pattern_id,
                memory_id_value or memory.workflow_id,
                memory.user_id,
                memory.project_id,
                base_command,
                sub_command,
                full_command,
                normalized_full,
                memory.command_template,
                cwd,
                normalized_cwd,
                semantic_description,
                source_type,
                origin,
                priority,
                execution_count,
                success_count,
                success_rate,
                bindings_json,
                "active",
                memory.last_executed_at,
                now,
                now,
            ),
        )
        return pattern_id

    def upsert_parameter_policy_from_text(
        self,
        text: str,
        *,
        user_id: str,
        project_id: str | None,
        memory_id_value: str | None = None,
        scenario_signature: str | None = None,
        target_base_command: str | None = None,
        target_sub_command: str | None = None,
        target_pattern_id: str | None = None,
    ) -> list[str]:
        """Extract explicit `参数 X 设置为 Y` policies from an OpenClaw teaching sentence."""
        policies = extract_parameter_policies(text)
        ids: list[str] = []
        for item in policies:
            ids.append(
                self.upsert_parameter_policy(
                    scenario_text=text,
                    param_name=item["param_name"],
                    param_value=item["param_value"],
                    user_id=user_id,
                    project_id=project_id,
                    memory_id_value=memory_id_value,
                    semantic_description=text,
                    scenario_signature=scenario_signature or infer_scenario_signature(text),
                    target_base_command=target_base_command,
                    target_sub_command=target_sub_command,
                    target_pattern_id=target_pattern_id,
                )
            )
        return ids

    def upsert_parameter_policy(
        self,
        *,
        scenario_text: str,
        param_name: str,
        param_value: str,
        user_id: str,
        project_id: str | None,
        memory_id_value: str | None = None,
        semantic_description: str | None = None,
        scenario_signature: str | None = None,
        target_base_command: str | None = None,
        target_sub_command: str | None = None,
        target_pattern_id: str | None = None,
    ) -> str:
        """Insert an active taught parameter policy, superseding older same-scope policies."""
        now = utc_now_iso()
        scenario_signature = scenario_signature or infer_scenario_signature(semantic_description or scenario_text)
        existing = self.fetch_one(
            """
            SELECT * FROM cli_parameter_policy
            WHERE user_id = ?
              AND COALESCE(project_id, '') = COALESCE(?, '')
              AND COALESCE(scenario_signature, '') = COALESCE(?, '')
              AND COALESCE(target_sub_command, '') = COALESCE(?, '')
              AND param_name = ?
              AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id, project_id, scenario_signature, target_sub_command, param_name),
        )
        policy_id = memory_id()
        if existing and existing.get("param_value") != param_value:
            self.execute(
                """
                UPDATE cli_parameter_policy
                SET status = 'superseded',
                    superseded_by = ?,
                    updated_at = ?
                WHERE policy_id = ?
                """,
                (policy_id, now, existing["policy_id"]),
            )
        self.execute(
            """
            INSERT INTO cli_parameter_policy (
                policy_id, memory_id, user_id, project_id, scenario_text,
                scenario_signature, semantic_description, target_base_command, target_sub_command,
                target_pattern_id, param_name, param_value, source_type,
                memory_origin, active_priority, binding_status, status,
                overwrite_of, superseded_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                policy_id,
                memory_id_value,
                user_id,
                project_id,
                scenario_text,
                scenario_signature,
                semantic_description,
                target_base_command,
                target_sub_command,
                target_pattern_id,
                param_name,
                param_value,
                "openclaw",
                "taught_param",
                1.0,
                "unbound",
                "active",
                existing["policy_id"] if existing and existing.get("param_value") != param_value else None,
                None,
                now,
                now,
            ),
        )
        return policy_id

    def list_patterns(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List active command patterns scoped by user/project."""
        clauses = ["user_id = ?", "status = 'active'"]
        params: list[Any] = [user_id]
        if project_id is not None:
            clauses.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)
        params.append(limit)
        rows = self.fetch_all(
            f"""
            SELECT * FROM cli_command_pattern
            WHERE {" AND ".join(clauses)}
            ORDER BY active_priority DESC, execution_count DESC, updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [deserialize_pattern(row) for row in rows]

    def list_parameter_policies(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List active taught parameter policies scoped by user/project."""
        clauses = ["user_id = ?", "status = 'active'"]
        params: list[Any] = [user_id]
        if project_id is not None:
            clauses.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)
        params.append(limit)
        return self.fetch_all(
            f"""
            SELECT * FROM cli_parameter_policy
            WHERE {" AND ".join(clauses)}
            ORDER BY active_priority DESC, updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )

    def find_top_parameter_policy(
        self,
        *,
        user_id: str,
        project_id: str | None,
        param_name: str,
        scenario_signature: str | None = None,
        target_sub_command: str | None = None,
    ) -> dict[str, Any] | None:
        """Find the most relevant active policy for write-time conflict judgment."""
        rows = self.fetch_all(
            """
            SELECT *,
                CASE
                    WHEN COALESCE(scenario_signature, '') = COALESCE(?, '') THEN 2
                    ELSE 0
                END +
                CASE
                    WHEN COALESCE(target_sub_command, '') = COALESCE(?, '') THEN 1
                    ELSE 0
                END AS match_score
            FROM cli_parameter_policy
            WHERE user_id = ?
              AND COALESCE(project_id, '') = COALESCE(?, '')
              AND param_name = ?
              AND status = 'active'
            ORDER BY match_score DESC, active_priority DESC, updated_at DESC
            LIMIT 1
            """,
            (scenario_signature, target_sub_command, user_id, project_id, param_name),
        )
        return rows[0] if rows else None

    def mark_parameter_policy_status(
        self,
        policy_id: str,
        *,
        status: str,
        superseded_by: str | None = None,
    ) -> None:
        """Update a parameter policy status for LLM write-time decisions."""
        self.execute(
            """
            UPDATE cli_parameter_policy
            SET status = ?,
                superseded_by = COALESCE(?, superseded_by),
                updated_at = ?
            WHERE policy_id = ?
            """,
            (status, superseded_by, utc_now_iso(), policy_id),
        )

    def sub_command_frequency(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
    ) -> dict[str, int]:
        """Return execution-count frequency grouped by sub-command."""
        clauses = ["user_id = ?", "status = 'active'"]
        params: list[Any] = [user_id]
        if project_id is not None:
            clauses.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)
        rows = self.fetch_all(
            f"""
            SELECT sub_command, SUM(execution_count) AS frequency
            FROM cli_command_pattern
            WHERE {" AND ".join(clauses)}
            GROUP BY sub_command
            """,
            tuple(params),
        )
        return {str(row["sub_command"]): int(row["frequency"] or 0) for row in rows}


def render_command(template: str, bindings: list[ParameterBinding]) -> str:
    """Render a command template using the strongest stored parameter binding values."""
    rendered = template
    for binding in sorted(bindings, key=lambda item: -item.frequency):
        rendered = rendered.replace(f"{{{binding.param_name}}}", binding.param_value)
    return rendered


def split_command_identity(command: str) -> tuple[str, str]:
    """Return base command and sub-command from a full command string."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return "", ""
    base = tokens[0]
    if base in {"python", "python3", "node", "deno", "bun"} and len(tokens) >= 2:
        return base, f"{base} {tokens[1]}"
    if len(tokens) >= 2 and not tokens[1].startswith("-"):
        return base, f"{base} {tokens[1]}"
    return base, base


def normalize_command_text(command: str) -> str:
    """Normalize whitespace and path separators for stable command comparison."""
    return " ".join(command.replace("\\", "/").split()).lower()


def normalize_path(value: str) -> str:
    """Normalize a cwd/path string without requiring it to exist."""
    if not value:
        return ""
    return str(Path(value.replace("\\", "/"))).replace("\\", "/").lower()


def extract_parameter_policies(text: str) -> list[dict[str, str]]:
    """Extract explicit Chinese parameter policies like `参数 stage 设置为 staging`."""
    cleaned = clean_text(text)
    patterns = [
        r"参数\s*([A-Za-z0-9_.-]+)\s*(?:设置为|设为|=|用)\s*([A-Za-z0-9_.:/-]+)",
        r"--([A-Za-z0-9_.-]+)\s*(?:设置为|设为|=|用)\s*([A-Za-z0-9_.:/-]+)",
    ]
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, cleaned):
            key = (match.group(1), match.group(2))
            if key in seen:
                continue
            seen.add(key)
            result.append({"param_name": key[0], "param_value": key[1]})
    return result


def infer_scenario_signature(text: str) -> str:
    """Infer a stable scenario signature without parameter values for conflict grouping."""
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    for item in extract_parameter_policies(cleaned):
        cleaned = cleaned.replace(item["param_name"], " ")
        cleaned = cleaned.replace(item["param_value"], " ")
    cleaned = re.sub(r"(参数|设置为|设为|记住|以后|下次|的时候|时|用|=|--)", " ", cleaned)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_.-]+", cleaned)
    stop = {"参数", "设置", "记住", "以后", "下次", "时候"}
    result: list[str] = []
    for token in tokens:
        if token in stop:
            continue
        if token not in result:
            result.append(token)
    return " ".join(result[:8])


def deserialize_pattern(row: dict[str, Any]) -> dict[str, Any]:
    """Deserialize JSON fields in a command pattern row."""
    row = dict(row)
    row["parameter_bindings"] = json.loads(row.get("parameter_bindings_json") or "[]")
    return row
