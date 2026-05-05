from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import MemoryItem, RankedMemory, RetrievalQuery, memory_item_from_core
from src.storage.cli_workflow_store import CLIWorkflowStore, split_command_identity
from src.storage.memory_core_store import MemoryCoreStore
from src.utils.text import clean_text

from .models import CLIWorkflowMemory, ParameterBinding

_COMMAND_QUERY_PREFIXES: set[str] = {
    "git", "docker", "docker-compose", "kubectl", "k", "helm",
    "npm", "npx", "yarn", "pnpm", "bun", "node", "deno",
    "uv", "pip", "pip3", "python", "python3", "pytest", "poetry",
    "go", "cargo", "make", "cmake", "gradle", "mvn",
    "terraform", "tofu", "ansible", "lark", "lark-cli",
    "curl", "wget", "ssh", "scp", "rsync", "gh", "glab",
}

_SEMANTIC_ALIASES: dict[str, list[str]] = {
    "测试": ["test", "pytest", "pnpm test", "npm test"],
    "检查": ["check", "lint", "ruff"],
    "修复": ["fix", "ruff", "lint"],
    "部署": ["deploy", "push", "rollout"],
    "日志": ["logs", "log"],
    "查看": ["get", "logs", "list"],
    "启动": ["run", "up", "start"],
    "回滚": ["rollback", "zero"],
}


@dataclass(slots=True)
class CLIWorkflowSearchResult:
    memory: CLIWorkflowMemory
    memory_item: MemoryItem
    score: float = 0.0
    match_reason: str = ""
    matched_fields: list[str] = field(default_factory=list)

    def to_ranked_memory(self, rank: int = 0) -> RankedMemory:
        self.memory_item.extra["workflow"] = self.memory.to_dict()
        self.memory_item.extra["matched_fields"] = list(self.matched_fields)
        return RankedMemory(
            item=self.memory_item,
            final_score=self.score,
            score_breakdown={"domain_score": self.score},
            rank=rank,
        )

    def to_suggestion(self) -> dict[str, Any]:
        return {
            "command_name": self.memory.command_name,
            "command_template": self.memory.command_template,
            "command_category": self.memory.command_category,
            "project_id": self.memory.project_id,
            "parameter_bindings": [
                {"param_name": pb.param_name, "param_value": pb.param_value, "frequency": pb.frequency}
                for pb in sorted(self.memory.parameter_bindings, key=lambda x: -x.frequency)
            ],
            "execution_count": self.memory.execution_count,
            "last_executed_at": self.memory.last_executed_at,
            "success_rate": self.memory.success_rate,
            "source_type": self.memory.source_type,
            "score": self.score,
        }

    def to_completion(self) -> list[str]:
        """输出补全候选列表。根据 matched_fields 决定补全内容。"""
        candidates: list[str] = []
        for pb in sorted(self.memory.parameter_bindings, key=lambda x: -x.frequency):
            candidates.append(f"--{pb.param_name} {pb.param_value}")
        return candidates


class CLIWorkflowRetriever:
    """CLI 工作流检索器，融合 MemoryCore 文本召回与结构化 CLI 行为表排序。"""

    def __init__(self, memory_store: MemoryCoreStore, cli_store: CLIWorkflowStore | None = None) -> None:
        """初始化检索器，cli_store 可选用于主动记忆优先和子命令频率混合排序。"""
        self.memory_store = memory_store
        self.cli_store = cli_store

    def retrieve(
        self,
        query: RetrievalQuery,
        *,
        limit: int = 10,
    ) -> list[CLIWorkflowSearchResult]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if not query.user_id:
            return []

        base_command = self._extract_base_command(query.query_text)

        rows = self._load_candidates(limit=limit)
        filtered = self._filter_candidates(rows, query, base_command=base_command)
        scored = self._score_matches(filtered, query)
        scored = self._apply_structured_scores(scored, query)
        scored.sort(key=lambda r: (-r.score, -(r.memory.execution_count or 0)))
        return scored[:limit]

    def _extract_base_command(self, query_text: str) -> str | None:
        """从明确的命令/前缀查询中提取基础命令，避免自然语言被硬过滤。"""
        import shlex
        try:
            tokens = shlex.split(query_text.strip())
        except ValueError:
            tokens = query_text.strip().split()
        for token in tokens:
            if token.startswith("-"):
                continue
            lowered = token.lower()
            if not re.fullmatch(r"[a-zA-Z0-9_.:/\\-]+", lowered):
                return None
            if lowered in _COMMAND_QUERY_PREFIXES or len(lowered) <= 4:
                return lowered
            return None
        return None

    def _load_candidates(self, *, limit: int) -> list[dict[str, Any]]:
        active_rows = self.memory_store.search_memory_candidates(
            domain="cli_workflow",
            status="active",
            limit=max(limit * 10, 100),
        )
        return active_rows

    def _filter_candidates(
        self,
        rows: list[dict[str, Any]],
        query: RetrievalQuery,
        *,
        base_command: str | None = None,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            if row.get("status") == "superseded":
                continue
            entities = _parse_entities(row)
            row_user = self._entity_value(entities, "user_id")
            row_project = self._entity_value(entities, "project_id")

            # 必须匹配 user_id（个人记忆隔离）
            if not row_user or row_user != query.user_id:
                continue

            # 如果 query 指定了 project_id，优先匹配
            if query.project_id and row_project and query.project_id != row_project:
                continue

            # 只在 query 可提取 base_command 时，按 command_name 子串匹配过滤
            if base_command:
                row_cmd_name = self._entity_value(entities, "command_name")
                if row_cmd_name and base_command not in row_cmd_name.lower():
                    continue

            result.append(row)
        return result

    def _score_matches(
        self,
        rows: list[dict[str, Any]],
        query: RetrievalQuery,
    ) -> list[CLIWorkflowSearchResult]:
        terms = self._extract_query_terms(query.query_text)
        results: list[CLIWorkflowSearchResult] = []
        query_lower = clean_text(query.query_text).lower()

        for row in rows:
            memory = CLIWorkflowMemory.from_memory_core(row)
            item = memory_item_from_core(row)
            search_text = self._row_search_text(row).lower()
            matched_fields: list[str] = []
            score = 0.0
            rendered_command = self._render_command(memory).lower()

            # 前缀补全：py/docker/npm run 等短前缀应优先匹配命令开头。
            prefix = self._extract_base_command(query.query_text)
            if prefix and (
                memory.command_name.lower().startswith(prefix)
                or rendered_command.startswith(prefix)
            ):
                score += 0.30
                matched_fields.append("prefix")

            # 命令名精确匹配
            if query_lower and memory.command_name.lower() in query_lower:
                score += 0.25
                matched_fields.append("command_name_exact")
            elif query_lower and any(
                word in memory.command_name.lower()
                for word in query_lower.split()
            ):
                score += 0.15
                matched_fields.append("command_name_partial")

            # 项目匹配
            if query.project_id and query.project_id == memory.project_id:
                score += 0.15
                matched_fields.append("project_id")

            # user 匹配
            if query.user_id and query.user_id == memory.user_id:
                score += 0.10
                matched_fields.append("user_id")

            # 关键词匹配
            if terms:
                matched_terms = [
                    term for term in terms
                    if term.lower() in search_text or term.lower() in rendered_command
                ]
                if matched_terms:
                    score += min(0.25, 0.08 * len(matched_terms))
                    matched_fields.append("keyword")

            # 参数名匹配（查询中包含参数名）
            if query_lower:
                for pb in memory.parameter_bindings:
                    if f"--{pb.param_name}" in query_lower or f"-{pb.param_name}" in query_lower:
                        score += 0.05
                        matched_fields.append(f"param:{pb.param_name}")
                        break

            # 频率分
            importance = float(row.get("importance") or 0.0)
            score += min(importance, 0.3) * 0.5

            # 新鲜度分
            freshness = float(row.get("freshness_score") or 0.0)
            score += min(freshness, 0.2) * 0.25

            # 置信度（成功率）
            confidence = float(row.get("confidence") or 0.0)
            score += min(confidence, 0.2) * 0.25

            # 同项目下的记忆加分
            if memory.project_id and query.project_id and memory.project_id == query.project_id:
                score += 0.05
                matched_fields.append("same_project")

            match_reason = "、".join(matched_fields) if matched_fields else "domain_fallback"
            results.append(
                CLIWorkflowSearchResult(
                    memory=memory,
                    memory_item=item,
                    score=min(score, 1.0),
                    match_reason=match_reason,
                    matched_fields=matched_fields,
                )
            )
        return results

    def _apply_structured_scores(
        self,
        results: list[CLIWorkflowSearchResult],
        query: RetrievalQuery,
    ) -> list[CLIWorkflowSearchResult]:
        """叠加结构化 CLI 表中的主动记忆优先级、参数策略和子命令频率。"""
        if self.cli_store is None or not query.user_id or not results:
            return results

        patterns = self.cli_store.list_patterns(
            user_id=query.user_id,
            project_id=query.project_id,
            limit=max(len(results) * 5, 50),
        )
        policies = self.cli_store.list_parameter_policies(
            user_id=query.user_id,
            project_id=query.project_id,
            limit=50,
        )
        pattern_by_memory_id = {
            str(pattern.get("memory_id")): pattern
            for pattern in patterns
            if pattern.get("memory_id")
        }
        sub_command_freq = self.cli_store.sub_command_frequency(
            user_id=query.user_id,
            project_id=query.project_id,
        )

        for result in results:
            pattern = pattern_by_memory_id.get(result.memory.workflow_id)
            _, sub_command = split_command_identity(self._render_command(result.memory))
            if pattern:
                sub_command = str(pattern.get("sub_command") or sub_command)
                origin = str(pattern.get("memory_origin") or "")
                if origin == "taught_command" and self._semantic_match(pattern, query):
                    result.score += 1.5
                    result.matched_fields.append("taught_command")
                elif origin == "taught_command":
                    result.score += 0.35
                    result.matched_fields.append("taught_command_scope")

            frequency = sub_command_freq.get(sub_command, 0)
            if frequency > 0:
                result.score += min(0.25, frequency / 200)
                result.matched_fields.append("sub_command_frequency")

            self._apply_parameter_policies(result, policies, query)

            result.match_reason = "、".join(result.matched_fields) if result.matched_fields else result.match_reason
        return results

    def _apply_parameter_policies(
        self,
        result: CLIWorkflowSearchResult,
        policies: list[dict[str, Any]],
        query: RetrievalQuery,
    ) -> None:
        """把 OpenClaw 主动教过的参数策略注入候选命令，并给予最高优先级加分。"""
        if not policies:
            return
        command_surface = f"{result.memory.command_template} {result.memory.command_name}".lower()
        bindings_by_name = {
            binding.param_name: binding
            for binding in result.memory.parameter_bindings
        }
        changed = False
        for policy in policies:
            if not self._semantic_match(policy, query):
                continue
            param_name = str(policy.get("param_name") or "")
            param_value = str(policy.get("param_value") or "")
            if not param_name or not param_value:
                continue
            if f"{{{param_name}}}" not in result.memory.command_template and f"--{param_name}".lower() not in command_surface:
                continue
            bindings_by_name[param_name] = ParameterBinding(
                param_name=param_name,
                param_value=param_value,
                frequency=1_000_000,
                semantics=str(policy.get("semantic_description") or policy.get("scenario_text") or ""),
            )
            result.score += 2.0
            result.matched_fields.append(f"taught_param:{param_name}")
            changed = True
        if changed:
            result.memory.parameter_bindings = list(bindings_by_name.values())

    def _semantic_match(self, item: dict[str, Any], query: RetrievalQuery) -> bool:
        """用轻量语义文本匹配判断结构化记忆是否适合当前查询。"""
        terms = self._extract_query_terms(query.query_text)
        if not terms:
            return True
        searchable = " ".join(
            str(part)
            for part in (
                item.get("semantic_description"),
                item.get("scenario_text"),
                item.get("full_command"),
                item.get("command_template"),
                item.get("sub_command"),
                item.get("param_name"),
                item.get("param_value"),
            )
            if part
        ).lower()
        return any(term.lower() in searchable for term in terms)

    def _extract_query_terms(self, query_text: str) -> list[str]:
        cleaned = clean_text(query_text)
        raw_terms = re.findall(r"[一-鿿]{2,}|[A-Za-z0-9_\-]{2,}", cleaned)
        stop_words = {"我们", "之前", "这个", "那个", "一下", "为什么", "帮我", "怎么"}
        result: list[str] = []
        for term in raw_terms:
            if term in stop_words or term.lower() in stop_words:
                continue
            if term not in result:
                result.append(term)
            for alias in _SEMANTIC_ALIASES.get(term, []):
                if alias not in result:
                    result.append(alias)
        return result

    @staticmethod
    def _render_command(memory: CLIWorkflowMemory) -> str:
        """用参数绑定渲染命令模板，供前缀、关键词和语义匹配使用。"""
        rendered = memory.command_template
        for pb in sorted(memory.parameter_bindings, key=lambda x: -x.frequency):
            rendered = rendered.replace(f"{{{pb.param_name}}}", pb.param_value)
        return rendered

    def _row_search_text(self, row: dict[str, Any]) -> str:
        entities = " ".join(row.get("entities") or row.get("entities_json") or [])
        tags = " ".join(row.get("tags") or row.get("tags_json") or [])
        return " ".join(
            clean_text(part)
            for part in (
                row.get("summary_text"),
                row.get("content_text"),
                row.get("source_ref"),
                entities,
                tags,
            )
            if part
        )

    @staticmethod
    def _entity_value(entities: list[str], prefix: str) -> str | None:
        marker = f"{prefix}:"
        for entity in entities:
            if entity.startswith(marker):
                return entity[len(marker):]
        return None


def _parse_entities(row: dict[str, Any]) -> list[str]:
    """从 DB 行中解析 entities 字段，兼容 entities_json JSON 字符串和 entities 列表。"""
    raw = row.get("entities") or row.get("entities_json") or []
    if isinstance(raw, str):
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(raw, list):
        return raw
    return []
