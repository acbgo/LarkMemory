"""记录完整检索链路用于调试和评测。

提供 context manager 风格的 API，自动追踪每个步骤的
输入摘要、输出摘要、耗时和嵌套结构。
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Generator

from ._types import RetrievalTrace, TraceStep

logger = logging.getLogger(__name__)
TracePersistFn = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# TraceContext — 单次检索的追踪上下文
# ---------------------------------------------------------------------------

class TraceContext:
    """管理一次检索请求的完整链路追踪。

    典型用法::

        tracer = RetrievalTracer()
        with tracer.start_trace("q-123") as ctx:
            with ctx.step("intent_analysis") as s:
                result = await analyzer.analyze(query)
                s.set_output({"primary": [...], "confidence": 0.9})
            with ctx.step("query_rewrite"):
                ...
            with ctx.step("fusion"):
                ...
            with ctx.step("rerank") as s:
                s.set_output({"result_count": 5})
        trace = ctx.trace  # 完整的 RetrievalTrace
    """

    def __init__(self, query_id: str) -> None:
        """初始化单次检索追踪上下文，输入 query_id 并准备步骤栈。"""
        self._query_id = query_id
        self._start = time.monotonic()
        self._steps: list[TraceStep] = []
        self._step_stack: list[TraceStep] = []
        self._finished = False
        self._metadata: dict[str, Any] = {}
        self._result_count = 0

    # ------------------------------------------------------------------
    # Step context manager
    # ------------------------------------------------------------------

    @contextmanager
    def step(
        self,
        name: str,
        *,
        input_summary: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[StepHandle, None, None]:
        """记录一个步骤。支持嵌套。"""
        ts = TraceStep(
            name=name,
            start_time=time.monotonic(),
            input_summary=input_summary or {},
            metadata=metadata or {},
        )

        handle = StepHandle(ts)
        self._step_stack.append(ts)

        try:
            yield handle
        except Exception as exc:
            ts.metadata["error"] = str(exc)
            raise
        finally:
            ts.end_time = time.monotonic()
            ts.duration_ms = (ts.end_time - ts.start_time) * 1000
            self._step_stack.pop()

            if self._step_stack:
                self._step_stack[-1].children.append(ts)
            else:
                self._steps.append(ts)

    # ------------------------------------------------------------------
    # 元数据与结束
    # ------------------------------------------------------------------

    def set_metadata(self, key: str, value: Any) -> None:
        """设置 trace 级元数据，输入键和值。"""
        self._metadata[key] = value

    def set_result_count(self, count: int) -> None:
        """设置最终结果数量，输入检索返回条数。"""
        self._result_count = count

    def finish(self) -> RetrievalTrace:
        """结束追踪并返回完整 trace。"""
        if self._finished:
            return self.trace

        self._finished = True
        end = time.monotonic()

        return RetrievalTrace(
            query_id=self._query_id,
            start_time=self._start,
            end_time=end,
            total_duration_ms=(end - self._start) * 1000,
            steps=list(self._steps),
            final_result_count=self._result_count,
            metadata=dict(self._metadata),
        )

    @property
    def trace(self) -> RetrievalTrace:
        """返回当前 RetrievalTrace；未完成时会先结束追踪。"""
        if not self._finished:
            return self.finish()
        return RetrievalTrace(
            query_id=self._query_id,
            start_time=self._start,
            end_time=self._steps[-1].end_time if self._steps else self._start,
            total_duration_ms=sum(s.duration_ms for s in self._steps),
            steps=list(self._steps),
            final_result_count=self._result_count,
            metadata=dict(self._metadata),
        )


class StepHandle:
    """step context manager 返回的句柄，用于设置输出和元数据。"""

    def __init__(self, step: TraceStep) -> None:
        """初始化步骤句柄，输入需要被补充信息的 TraceStep。"""
        self._step = step

    def set_input(self, data: dict[str, Any]) -> None:
        """合并步骤输入摘要，输入字段字典。"""
        self._step.input_summary.update(data)

    def set_output(self, data: dict[str, Any]) -> None:
        """合并步骤输出摘要，输入字段字典。"""
        self._step.output_summary.update(data)

    def set_metadata(self, key: str, value: Any) -> None:
        """设置步骤元数据，输入键和值。"""
        self._step.metadata[key] = value


# ---------------------------------------------------------------------------
# RetrievalTracer — 工厂 & 存储
# ---------------------------------------------------------------------------

class RetrievalTracer:
    """检索链路追踪器，负责创建和管理 TraceContext。

    Parameters
    ----------
    persist_fn:
        可选的持久化回调。当 trace 完成时，会调用此函数。
        签名: ``(trace_dict: dict) -> None``
    """

    def __init__(
        self,
        persist_fn: TracePersistFn | None = None,
    ) -> None:
        """初始化追踪器，输入可选持久化回调。"""
        self._persist_fn = persist_fn
        self._recent_traces: list[RetrievalTrace] = []
        self._max_recent = 100

    @contextmanager
    def start_trace(
        self,
        query_id: str | None = None,
    ) -> Generator[TraceContext, None, None]:
        """开始一次检索追踪。

        Parameters
        ----------
        query_id:
            查询 ID。为 None 时自动生成。
        """
        qid = query_id or f"q-{uuid.uuid4().hex[:12]}"
        ctx = TraceContext(qid)

        try:
            yield ctx
        finally:
            trace = ctx.finish()
            self._store(trace)

    def _store(self, trace: RetrievalTrace) -> None:
        """保存完成的 trace 到近期列表，并在提供回调时传出字典表示。"""
        self._recent_traces.append(trace)
        if len(self._recent_traces) > self._max_recent:
            self._recent_traces = self._recent_traces[-self._max_recent:]

        if self._persist_fn is not None:
            try:
                self._persist_fn(trace_to_dict(trace))
            except Exception:
                logger.warning("Failed to persist retrieval trace", exc_info=True)

    @property
    def recent_traces(self) -> list[RetrievalTrace]:
        """返回近期 trace 的列表副本。"""
        return list(self._recent_traces)

    def get_trace(self, query_id: str) -> RetrievalTrace | None:
        """按 query_id 从近期 trace 中查找单条记录。"""
        for t in reversed(self._recent_traces):
            if t.query_id == query_id:
                return t
        return None


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------

def _step_to_dict(step: TraceStep) -> dict[str, Any]:
    """将单个 TraceStep 递归序列化为字典。"""
    return {
        "name": step.name,
        "duration_ms": round(step.duration_ms, 2),
        "input_summary": step.input_summary,
        "output_summary": step.output_summary,
        "metadata": step.metadata,
        "children": [_step_to_dict(c) for c in step.children],
    }


def trace_to_dict(trace: RetrievalTrace) -> dict[str, Any]:
    """将 RetrievalTrace 序列化为可 JSON 化的字典。"""
    return {
        "query_id": trace.query_id,
        "total_duration_ms": round(trace.total_duration_ms, 2),
        "final_result_count": trace.final_result_count,
        "steps": [_step_to_dict(s) for s in trace.steps],
        "metadata": trace.metadata,
    }
