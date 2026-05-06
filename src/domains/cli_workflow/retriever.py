from __future__ import annotations

import logging
import shlex
import re
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import (
    FusedCandidate,
    MemoryDomain,
    MemoryItem,
    MemoryScope,
    RankedMemory,
    RetrievalQuery,
    Reranker,
    RewrittenQuery,
    memory_item_from_core,
)
from src.llm import EmbeddingClient, RerankClient
from src.storage.cli_workflow_store import CLIWorkflowStore, split_command_identity
from src.storage.embedding_store import EmbeddingStore
from src.storage.memory_core_store import MemoryCoreStore
from src.utils.text import clean_text

from .models import CLIWorkflowMemory, ParameterBinding


logger = logging.getLogger(__name__)

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

_QUERY_ANALYSIS_SYSTEM = (
    """
你是 CLI 工作流记忆系统的检索查询分析器。

你的任务是从用户查询中提取两类检索输入：
1. keywords：用于 BM25 的原始关键词；
2. semantic_query：用于向量检索的语义查询句。

你必须只输出一个合法 JSON 对象，不得输出 Markdown、解释文字、代码块或额外字段。

keywords 提取规则：
- 只提取用户查询中明确出现的有检索价值的词。
- 不做 query expansion。
- 不添加同义词、工具别名、英文翻译或用户没有提到的命令。
- 不生成完整命令。
- 不臆造项目名、路径、环境名、参数、端口、IP 或文件名。

keywords 应保留：
- 命令或工具名：如 git、docker、kubectl、npm、pnpm、python、conda、ssh；
- 子命令或动作词：如 deploy、build、test、start、run、logs、部署、启动、测试、构建、查看日志；
- 项目名、服务名、模块名、仓库名、分支名；
- 路径、文件名、配置名；
- 环境名：如 dev、test、staging、prod、预发、线上；
- 参数名和参数值：如 --env、--host、--port、staging、0.0.0.0、8080；
- 报错关键词、错误码。

keywords 不应包含：
- 的、了、一下、怎么、如何、那个、之前、上次、帮我、请问等虚词或泛化词；
- 没有明确出现在用户查询中的扩展词；
- 与 CLI 检索无关的情绪词或寒暄词。

semantic_query 规则：
- 用一句自然语言改写用户查询，表达其想检索的 CLI 工作流记忆。
- 保留用户明确提到的命令、工具、项目、环境、参数、路径、文件名。
- 可以补足“查找……相关 CLI 命令记忆”的语义，但不得添加新的事实或扩展关键词。
- 如果用户查询很短，也只基于原文生成语义查询，不要额外猜测。

示例：
用户查询：“demo-a 预发部署命令”
输出：
{
  "keywords": ["demo-a", "预发", "部署", "命令"],
  "semantic_query": "查找 demo-a 预发部署相关的 CLI 命令记忆"
}

用户查询：“上次那个 npm 启动命令”
输出：
{
  "keywords": ["npm", "启动", "命令"],
  "semantic_query": "查找之前记录的 npm 启动命令记忆"
}

用户查询：“看 k8s 日志怎么弄”
输出：
{
  "keywords": ["k8s", "日志"],
  "semantic_query": "查找 k8s 日志查看相关的 CLI 工作流记忆"
}

严格约束：
1. 只输出 JSON。
2. 不得输出 schema 之外的字段。
3. keywords 必须是字符串数组。
4. semantic_query 必须是字符串。
5. keywords 只能来自用户查询原文，不得扩展。
"""
)

_QUERY_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["keywords", "semantic_query"],
    "properties": {
        "keywords": {"type": "array", "items": {"type": "string"}},
        "semantic_query": {"type": "string"},
    },
}


@dataclass(slots=True)
class CLIQueryAnalysis:
    """CLI 检索查询分析结果，供 BM25、embedding 和 rerank 共用。"""

    keywords: list[str]
    semantic_query: str


@dataclass(slots=True)
class CommandIdentityQuery:
    """Structured command identity extracted from an explicit CLI query."""

    base_command: str
    sub_command: str | None = None
    script_path: str | None = None
    script_basename: str | None = None
    script_suffix: str | None = None
    has_absolute_path: bool = False


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

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        cli_store: CLIWorkflowStore | None = None,
        *,
        llm_client: Any | None = None,
        embedding_store: EmbeddingStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        rerank_client: RerankClient | None = None,
        min_relevance_score: float = 0.12,
    ) -> None:
        """初始化检索器，cli_store 可选用于主动记忆优先和子命令频率混合排序。"""
        self.memory_store = memory_store
        self.cli_store = cli_store
        self.llm_client = llm_client
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client
        self.min_relevance_score = min_relevance_score

    def retrieve(
        self,
        query: RetrievalQuery,
        *,
        limit: int = 10,
    ) -> list[CLIWorkflowSearchResult]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        direct_identity = self._extract_explicit_command_identity(query)
        if direct_identity is None:
            logger.debug(
                "action=cli_direct_identity_missing query_text=%s query_user_id=%s project_id=%s",
                query.query_text,
                query.user_id,
                query.project_id,
            )
        else:
            logger.debug(
                "action=cli_direct_identity_extracted query_text=%s query_user_id=%s project_id=%s "
                "base_command=%s sub_command=%s script_path=%s script_basename=%s",
                query.query_text,
                query.user_id,
                query.project_id,
                direct_identity.base_command,
                direct_identity.sub_command,
                direct_identity.script_path,
                direct_identity.script_basename,
            )
        direct_results = self._retrieve_direct_sub_command(query, direct_identity, limit=limit)
        if direct_results:
            return direct_results[:limit]

        if not query.user_id:
            return []

        base_command = self._extract_base_command(query.query_text)
        analysis = self._analyze_query(query)

        rows = self._load_candidates(query=query, analysis=analysis, limit=limit)
        filtered = self._filter_candidates(rows, query, base_command=base_command)
        scored = self._score_matches(filtered, query)
        scored = self._apply_structured_scores(scored, query)
        scored = self._rerank_results(scored, query, analysis, limit=limit)
        scored.sort(key=lambda r: (-r.score, -(r.memory.execution_count or 0)))
        scored = self._filter_low_confidence(scored, query)
        return scored[:limit]

    def _analyze_query(self, query: RetrievalQuery) -> CLIQueryAnalysis:
        """先用 LLM 提取关键词；不可用时退回规则关键词。"""
        fallback = CLIQueryAnalysis(
            keywords=self._extract_query_terms(query.query_text),
            semantic_query=clean_text(query.query_text),
        )
        if self.llm_client is None:
            return fallback
        try:
            raw = _run_async(
                self.llm_client.ajson(
                    _QUERY_ANALYSIS_SYSTEM,
                    query.query_text,
                    schema=_QUERY_ANALYSIS_SCHEMA,
                    temperature=0,
                    max_tokens=256,
                )
            )
        except Exception:
            return fallback
        keywords = _string_list(raw.get("keywords"))
        semantic_query = clean_text(str(raw.get("semantic_query") or "")) or fallback.semantic_query
        return CLIQueryAnalysis(keywords=keywords or fallback.keywords, semantic_query=semantic_query)

    def _extract_explicit_command_identity(self, query: RetrievalQuery) -> CommandIdentityQuery | None:
        """Extract an explicit command/sub-command from OpenClaw-style parameter recommendation text."""
        try:
            tokens = shlex.split(query.query_text.strip(), posix=False)
        except ValueError:
            tokens = query.query_text.strip().split()
        command_tokens: list[str] = []
        for token in tokens:
            cleaned = token.strip("\"'“”‘’`，,。？?：:")
            if not cleaned:
                continue
            if cleaned.startswith("-"):
                break
            lowered = cleaned.lower()
            if not command_tokens:
                if lowered not in _COMMAND_QUERY_PREFIXES:
                    continue
                command_tokens.append(cleaned)
                continue
            if re.search(r"[\u4e00-\u9fff]", cleaned):
                break
            command_tokens.append(cleaned)
            if command_tokens[0].lower() in {"python", "python3", "node", "deno", "bun"}:
                break
            if len(command_tokens) >= 3:
                break
        if not command_tokens:
            return None
        base = command_tokens[0]
        if base.lower() in {"python", "python3", "node", "deno", "bun"}:
            if len(command_tokens) < 2 or not _looks_like_script_path(command_tokens[1]):
                return None
            return self._script_identity(base, command_tokens[1], query)
        sub_command = " ".join(command_tokens[:3 if len(command_tokens) >= 3 else len(command_tokens)])
        return CommandIdentityQuery(base_command=base, sub_command=sub_command)

    def _script_identity(self, base: str, script_path: str, query: RetrievalQuery) -> CommandIdentityQuery:
        """Build a script command identity, using cwd only when the query supplies one."""
        normalized = _normalize_path_text(script_path)
        cwd = ""
        if isinstance(query.session_context, dict):
            cwd = str(query.session_context.get("cwd") or "")
        has_absolute = _is_absolute_path(normalized)
        absolute_path = normalized
        if cwd and not has_absolute:
            absolute_path = _join_path_text(cwd, normalized)
            has_absolute = True
        parts = [part for part in normalized.split("/") if part]
        basename = parts[-1] if parts else normalized
        suffix = "/".join(parts[-2:]) if len(parts) >= 2 else basename
        return CommandIdentityQuery(
            base_command=base,
            sub_command=f"{base} {absolute_path}" if has_absolute else f"{base} {normalized}",
            script_path=absolute_path if has_absolute else normalized,
            script_basename=basename,
            script_suffix=suffix,
            has_absolute_path=has_absolute,
        )

    def _retrieve_direct_sub_command(
        self,
        query: RetrievalQuery,
        identity: CommandIdentityQuery | None,
        *,
        limit: int,
    ) -> list[CLIWorkflowSearchResult]:
        """Directly retrieve command patterns when the query names a concrete sub-command."""
        if self.cli_store is None or identity is None:
            return []
        exact_sub_command = None if identity.script_path else identity.sub_command
        patterns = self.cli_store.find_patterns_by_command_identity(
            user_id=None,
            project_id=None,
            base_command=identity.base_command,
            sub_command=exact_sub_command,
            limit=max(limit * 10, 100),
        )
        logger.debug(
            "action=cli_direct_pattern_lookup query_user_id=%s user_filter_ignored=%s project_id=%s "
            "project_filter_ignored=%s base_command=%s sub_command=%s sql_sub_command=%s pattern_count=%s",
            query.user_id,
            True,
            query.project_id,
            True,
            identity.base_command,
            identity.sub_command,
            exact_sub_command,
            len(patterns),
        )
        matches: list[tuple[float, dict[str, Any]]] = []
        for pattern in patterns:
            score = self._command_identity_match_score(pattern, identity, query)
            if score <= 0:
                continue
            matches.append((score, pattern))
        logger.debug(
            "action=cli_direct_pattern_scored query_user_id=%s project_id=%s base_command=%s "
            "sub_command=%s matched_count=%s top_matches=%s",
            query.user_id,
            query.project_id,
            identity.base_command,
            identity.sub_command,
            len(matches),
            [
                {
                    "user_id": pattern.get("user_id"),
                    "project_id": pattern.get("project_id"),
                    "sub_command": pattern.get("sub_command"),
                    "execution_count": pattern.get("execution_count"),
                    "command_template": pattern.get("command_template"),
                    "score": score,
                }
                for score, pattern in matches[:3]
            ],
        )
        if not matches:
            return []
        policies = (
            self.cli_store.list_parameter_policies(
                user_id=query.user_id,
                project_id=query.project_id,
                limit=100,
            )
            if query.user_id
            else []
        )
        results = [
            self._pattern_to_search_result(pattern, score, policies, query)
            for score, pattern in sorted(
                matches,
                key=lambda item: (
                    -item[0],
                    -float(item[1].get("active_priority") or 0.0),
                    -int(item[1].get("execution_count") or 0),
                    -float(item[1].get("success_rate") or 0.0),
                ),
            )
        ]
        return results

    def _command_identity_match_score(
        self,
        pattern: dict[str, Any],
        identity: CommandIdentityQuery,
        query: RetrievalQuery,
    ) -> float:
        """Score direct command identity matches, degrading gracefully without cwd."""
        if str(pattern.get("base_command") or "").lower() != identity.base_command.lower():
            return 0.0
        pattern_surface = _normalize_path_text(
            " ".join(
                str(part)
                for part in (
                    pattern.get("sub_command"),
                    pattern.get("full_command"),
                    pattern.get("command_template"),
                )
                if part
            )
        )
        pattern_sub = _normalize_path_text(str(pattern.get("sub_command") or ""))
        score = 0.0
        if identity.sub_command and pattern_sub == _normalize_path_text(identity.sub_command):
            score += 10.0
        if identity.script_suffix and identity.script_suffix.lower() in pattern_surface.lower():
            score += 7.0
        if identity.script_basename and re.search(
            rf"(^|/){re.escape(identity.script_basename.lower())}(\s|$)",
            pattern_surface.lower(),
        ):
            score += 5.0
        if not identity.script_path and identity.sub_command and _normalize_path_text(identity.sub_command).lower() in pattern_surface.lower():
            score += 4.0
        if query.project_id and str(pattern.get("project_id") or "") == query.project_id:
            score += 2.0
        score += min(int(pattern.get("execution_count") or 0), 50) / 100
        return score

    def _pattern_to_search_result(
        self,
        pattern: dict[str, Any],
        score: float,
        policies: list[dict[str, Any]],
        query: RetrievalQuery,
    ) -> CLIWorkflowSearchResult:
        """Convert a structured command pattern into a retriever result."""
        memory = self._memory_from_pattern(pattern)
        item = MemoryItem(
            memory_id=memory.workflow_id,
            domain=MemoryDomain.CLI_WORKFLOW,
            memory_type="cli_workflow",
            content_text=memory.build_content_text(),
            importance=min(1.0, max(0.0, memory.execution_count / 100)),
            confidence=memory.success_rate,
            status="active",
            scope=MemoryScope.USER,
            summary_text=memory.build_summary_text(),
            tags=[f"param:{pb.param_name}={pb.param_value}" for pb in memory.parameter_bindings],
            entities=[
                f"user_id:{memory.user_id}",
                *([f"project_id:{memory.project_id}"] if memory.project_id else []),
                f"command_name:{memory.command_name}",
            ],
            source_ref=memory.project_id or "",
            created_at=pattern.get("created_at"),
            updated_at=pattern.get("updated_at"),
        )
        result = CLIWorkflowSearchResult(
            memory=memory,
            memory_item=item,
            score=min(3.0, 1.0 + score / 10),
            match_reason="direct_sub_command",
            matched_fields=["direct_sub_command", "frequency_pattern"],
        )
        self._apply_direct_parameter_policies(result, pattern, policies, query)
        return result

    @staticmethod
    def _memory_from_pattern(pattern: dict[str, Any]) -> CLIWorkflowMemory:
        """Build CLIWorkflowMemory from a structured command pattern row."""
        bindings = [
            ParameterBinding(
                param_name=str(item.get("param_name") or ""),
                param_value=str(item.get("param_value") or ""),
                frequency=int(item.get("frequency") or 1),
                semantics=item.get("semantics"),
            )
            for item in pattern.get("parameter_bindings") or []
            if item.get("param_name") and item.get("param_value")
        ]
        command_name = _command_name_from_pattern(pattern)
        return CLIWorkflowMemory(
            workflow_id=str(pattern.get("memory_id") or pattern.get("pattern_id") or ""),
            user_id=str(pattern.get("user_id") or ""),
            command_template=str(pattern.get("command_template") or pattern.get("full_command") or command_name),
            command_name=command_name,
            command_category=_infer_command_category(command_name),
            project_id=pattern.get("project_id"),
            semantic_description=pattern.get("semantic_description"),
            parameter_bindings=bindings,
            execution_count=int(pattern.get("execution_count") or 1),
            last_executed_at=pattern.get("last_executed_at") or pattern.get("updated_at"),
            success_count=int(pattern.get("success_count") or 0),
            source_type=str(pattern.get("source_type") or "shell"),
        )

    def _apply_direct_parameter_policies(
        self,
        result: CLIWorkflowSearchResult,
        pattern: dict[str, Any],
        policies: list[dict[str, Any]],
        query: RetrievalQuery,
    ) -> None:
        """Apply actively taught params to direct command-frequency results first."""
        if not policies:
            return
        pattern_id = str(pattern.get("pattern_id") or "")
        sub_command = _normalize_path_text(str(pattern.get("sub_command") or ""))
        bindings_by_name = {binding.param_name: binding for binding in result.memory.parameter_bindings}
        for policy in policies:
            policy_pattern = str(policy.get("target_pattern_id") or "")
            policy_sub = _normalize_path_text(str(policy.get("target_sub_command") or ""))
            bound = (
                (policy_pattern and pattern_id and policy_pattern == pattern_id)
                or (policy_sub and sub_command and policy_sub == sub_command)
                or self._semantic_match(policy, query)
            )
            if not bound:
                continue
            param_name = str(policy.get("param_name") or "")
            param_value = str(policy.get("param_value") or "")
            if not param_name or not param_value:
                continue
            bindings_by_name[param_name] = ParameterBinding(
                param_name=param_name,
                param_value=param_value,
                frequency=1_000_000,
                semantics=str(policy.get("semantic_description") or policy.get("scenario_text") or ""),
            )
            result.score += 2.0
            result.matched_fields.append(f"taught_param:{param_name}")
        result.memory.parameter_bindings = list(bindings_by_name.values())
        result.match_reason = "、".join(result.matched_fields)

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

    def _load_candidates(
        self,
        *,
        query: RetrievalQuery,
        analysis: CLIQueryAnalysis,
        limit: int,
    ) -> list[dict[str, Any]]:
        active_rows = self.memory_store.search_memory_candidates(
            domain="cli_workflow",
            status="active",
            limit=max(limit * 10, 100),
        )
        return self._merge_recall_rows(
            [
                (active_rows, "scan"),
                (self._load_bm25_candidates(analysis, limit=limit), "bm25"),
                (self._load_embedding_candidates(query, analysis, limit=limit), "embedding"),
            ]
        )

    def _load_bm25_candidates(
        self,
        analysis: CLIQueryAnalysis,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """用 LLM/规则关键词走 MemoryCore FTS5 BM25 召回。"""
        query_text = clean_text(" ".join(analysis.keywords)) or analysis.semantic_query
        if not query_text:
            return []
        hits = self.memory_store.search_bm25(
            query_text,
            domain="cli_workflow",
            status="active",
            limit=max(limit * 3, 20),
        )
        memory_ids = [str(hit["memory_id"]) for hit in hits]
        rows = self.memory_store.batch_get_memories(memory_ids)
        score_by_id = {str(hit["memory_id"]): float(hit.get("bm25_score") or 0.0) for hit in hits}
        for row in rows:
            row["_bm25_score"] = score_by_id.get(str(row.get("memory_id")), 0.0)
        return rows

    def _load_embedding_candidates(
        self,
        query: RetrievalQuery,
        analysis: CLIQueryAnalysis,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """用 semantic_query 对 semantic_description 向量索引召回。"""
        if self.embedding_store is None or self.embedding_client is None:
            return []
        semantic_query = analysis.semantic_query or query.query_text
        if not clean_text(semantic_query):
            return []
        try:
            vector = self.embedding_client.embed_text(semantic_query)
            hits = self.embedding_store.query_by_embedding(
                vector,
                domain="cli_workflow",
                top_k=max(limit * 3, 20),
                filters={"user_id": query.user_id} if query.user_id else None,
            )
        except Exception:
            return []
        memory_ids = [str(hit["memory_id"]) for hit in hits]
        rows = self.memory_store.batch_get_memories(memory_ids)
        score_by_id: dict[str, float] = {}
        for hit in hits:
            distance = hit.get("distance")
            score = 0.0
            if isinstance(distance, int | float):
                score = max(0.0, 1.0 - float(distance))
            score_by_id[str(hit["memory_id"])] = score
        for row in rows:
            row["_embedding_score"] = score_by_id.get(str(row.get("memory_id")), 0.0)
        return rows

    def _merge_recall_rows(self, groups: list[tuple[list[dict[str, Any]], str]]) -> list[dict[str, Any]]:
        """合并 scan/BM25/embedding 召回结果并保留每条记忆的召回来源。"""
        merged: dict[str, dict[str, Any]] = {}
        for rows, source in groups:
            for row in rows:
                memory_id = str(row.get("memory_id") or "")
                if not memory_id:
                    continue
                target = merged.setdefault(memory_id, dict(row))
                fields = target.setdefault("_recall_sources", [])
                if source not in fields:
                    fields.append(source)
                for key in ("_bm25_score", "_embedding_score"):
                    if row.get(key) is not None:
                        target[key] = max(float(target.get(key) or 0.0), float(row.get(key) or 0.0))
        return list(merged.values())

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
            recall_sources = row.get("_recall_sources") or []
            if "bm25" in recall_sources:
                score += 0.35 + min(0.2, float(row.get("_bm25_score") or 0.0) * 0.2)
                matched_fields.append("bm25")
            if "embedding" in recall_sources:
                score += 0.35 + min(0.2, float(row.get("_embedding_score") or 0.0) * 0.2)
                matched_fields.append("embedding")

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

    def _rerank_results(
        self,
        results: list[CLIWorkflowSearchResult],
        query: RetrievalQuery,
        analysis: CLIQueryAnalysis,
        *,
        limit: int,
    ) -> list[CLIWorkflowSearchResult]:
        """对合并候选做可选 rerank，并把 rerank 分回写到领域结果。"""
        if self.rerank_client is None or len(results) <= 1:
            return results
        candidates = [
            FusedCandidate(
                item=result.memory_item,
                source_domain=result.memory_item.domain,
                domain_rank=index + 1,
                fusion_score=max(result.score, 0.01),
            )
            for index, result in enumerate(results)
        ]
        rewritten = RewrittenQuery(
            original=query,
            rewritten_text=analysis.semantic_query or query.query_text,
            query_variants=[query.query_text, analysis.semantic_query],
            extracted_topics=analysis.keywords,
        )
        try:
            ranked = _run_async(
                Reranker(rerank_client=self.rerank_client).rerank(
                    candidates,
                    rewritten,
                    top_k=max(limit, len(results)),
                )
            )
        except Exception:
            return results
        by_id = {result.memory.workflow_id: result for result in results}
        reranked: list[CLIWorkflowSearchResult] = []
        for ranked_memory in ranked:
            result = by_id.get(ranked_memory.item.memory_id)
            if result is None:
                continue
            result.score = max(result.score, ranked_memory.final_score)
            result.matched_fields.append("rerank")
            result.match_reason = "、".join(result.matched_fields)
            reranked.append(result)
        return reranked or results

    def _filter_low_confidence(
        self,
        results: list[CLIWorkflowSearchResult],
        query: RetrievalQuery,
    ) -> list[CLIWorkflowSearchResult]:
        """Filter weak matches by score and at least one meaningful relevance signal."""
        if not results:
            return []
        if not clean_text(query.query_text):
            return results
        if results[0].score < self.min_relevance_score:
            return []
        strong = [
            result
            for result in results
            if result.score >= self.min_relevance_score and self._has_strong_relevance_signal(result)
        ]
        return strong

    @staticmethod
    def _has_strong_relevance_signal(result: CLIWorkflowSearchResult) -> bool:
        """Return true when a candidate has a real lexical/vector/taught-command match."""
        strong_fields = {
            "bm25",
            "embedding",
            "keyword",
            "prefix",
            "command_name_exact",
            "command_name_partial",
            "taught_command",
            "rerank",
        }
        fields = set(result.matched_fields)
        return bool(fields & strong_fields) or any(field.startswith("taught_param:") for field in fields)

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


def _run_async(awaitable: Any) -> Any:
    """在同步 retriever 中运行可选 LLM/rerank 异步调用。"""
    try:
        import asyncio
        asyncio.get_running_loop()
    except RuntimeError:
        import asyncio
        return asyncio.run(awaitable)
    raise RuntimeError("CLIWorkflowRetriever sync API cannot run inside an active event loop")


def _looks_like_script_path(value: str) -> bool:
    lowered = value.lower()
    return (
        "/" in value
        or "\\" in value
        or lowered.endswith((".py", ".js", ".ts", ".mjs", ".cjs"))
    )


def _command_name_from_pattern(pattern: dict[str, Any]) -> str:
    return str(
        pattern.get("sub_command")
        or pattern.get("full_command")
        or pattern.get("command_template")
        or pattern.get("command_name")
        or pattern.get("base_command")
        or ""
    )


def _infer_command_category(command_name: str) -> str:
    if not command_name:
        return "general"
    base = command_name.split()[0].lower()
    category_map: dict[str, str] = {
        "git": "vcs", "gh": "vcs", "glab": "vcs",
        "docker": "container", "docker-compose": "container",
        "kubectl": "orchestration", "k": "orchestration", "helm": "orchestration",
        "npm": "package", "npx": "package", "yarn": "package",
        "pnpm": "package", "bun": "package", "uv": "package",
        "pip": "package", "pip3": "package", "poetry": "package",
        "go": "build", "cargo": "build", "rustc": "build",
        "make": "build", "cmake": "build", "gradle": "build", "mvn": "build",
        "terraform": "iac", "tofu": "iac", "ansible": "iac",
        "lark": "lark", "lark-cli": "lark",
        "curl": "network", "wget": "network", "ssh": "network",
        "gcloud": "cloud", "aws": "cloud", "az": "cloud",
        "python": "script", "python3": "script", "node": "script",
    }
    return category_map.get(base, "general")


def _normalize_path_text(value: str) -> str:
    return value.replace("\\", "/").strip().strip("\"'").lower()


def _is_absolute_path(value: str) -> bool:
    if value and (value[0] == "/" or (len(value) >= 2 and value[1] == ":")):
        return True
    return False


def _join_path_text(cwd: str, relative: str) -> str:
    cwd_norm = _normalize_path_text(cwd)
    rel_norm = _normalize_path_text(relative)
    return cwd_norm.rstrip("/") + "/" + rel_norm.lstrip("/")


def _string_list(value: Any) -> list[str]:
    """把 LLM 返回数组规整成非空去重字符串列表。"""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        cleaned = clean_text(str(item))
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result
