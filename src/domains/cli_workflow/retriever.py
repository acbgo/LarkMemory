from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import MemoryItem, RankedMemory, RetrievalQuery, memory_item_from_core
from src.storage import MemoryCoreStore
from src.utils.text import clean_text

from .models import CLIWorkflowMemory


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

    def __init__(self, memory_store: MemoryCoreStore) -> None:
        self.memory_store = memory_store

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
        scored.sort(key=lambda r: (-r.score, -(r.memory.execution_count or 0)))
        return scored[:limit]

    def _extract_base_command(self, query_text: str) -> str | None:
        """从查询文本中提取基础命令名（第一个非选项 token）。"""
        import shlex
        try:
            tokens = shlex.split(query_text.strip())
        except ValueError:
            tokens = query_text.strip().split()
        for token in tokens:
            if not token.startswith("-"):
                return token.lower()
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
            if terms and any(term.lower() in search_text for term in terms):
                score += 0.15
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

    def _extract_query_terms(self, query_text: str) -> list[str]:
        cleaned = clean_text(query_text)
        raw_terms = re.findall(r"[一-鿿]{2,}|[A-Za-z0-9_\-]{2,}", cleaned)
        stop_words = {"我们", "之前", "这个", "那个", "一下", "为什么", "帮我", "怎么"}
        result: list[str] = []
        for term in raw_terms:
            if term in stop_words or term.lower() in stop_words:
                continue
     find .tmp-demo -type f -name "*.py" -maxdepth 2
     tar -czf .tmp-demo/cli-test.tgz --exclude "*.bak" .tmp-demo/cli_dummy.py
     grep -n --ignore-case --context 2 "dummy" .tmp-demo/cli_dummy.py
     四、测试后看建议
     
     执行几条后等一下：
     
     sleep 2
     然后查建议：
     
     lark-memory suggest git
     lark-memory suggest tar
     lark-memory suggest grep
     lark-memory suggest find
     测试补全：
     
     lark-memory complete -- "git log " ""
     lark-memory complete -- "tar " ""
     lark-memory complete -- "grep " ""
     lark-memory complete -- "find " ""
     小提醒：当前方向 A 的 extractor 对“已知工具链”更敏感，git、docker、kubectl、npm、uv、curl、lark-cli 这类更容易被记住。grep/find/tar 如果没在已知工具链列表里，只有带 flag 时才更可能被抽取，适合用来测边界。
     
     
     
     
     
     19:27
     git grep -n "cli_workflow" -- src tests这个指令怎么推出
     19:31
     
     
     你是想问“这个命令怎么退出”对吧？
     
     git grep -n "cli_workflow" -- src tests 如果输出很多，通常会进入分页器 less。退出按：
     
     q
     如果它还在执行、没进入分页器，可以按：
     
     Ctrl + C
     下次不想进入分页器，可以这样跑：
     
     git --no-pager grep -n "cli_workflow" -- src tests
     或者限制输出数量：
     
     git --no-pager grep -n "cli_workflow" -- src tests | head -20
     
     
     
     
     19:31
     
     
     
     
     
     默认权限
     
     5.5
     中
     
     
     
     本地模式
     
     main
     
     分支详情
     
     更改
     +5,397
     -9
     
     Git 操作
     GitHub CLI 不可用
     
     生成结果
     
     127.0.0.1:8765
     
     Scenario Analysis.md
     
     team_retention_llm_prompt.md
     
     feishu-integration-usage.md
     
     来源
     网页搜索       if term not in result:
                result.append(term)
        return result

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
