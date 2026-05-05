from __future__ import annotations

import logging

from fastapi import APIRouter

from src.schemas import (
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BenchmarkStatusResponse,
)
from src.utils.ids import benchmark_run_id

from benchmark.runner.runner import BenchmarkRunner
from benchmark.runner.reporter import to_json
from benchmark.runner.types import RunnerConfig

router = APIRouter(prefix="/api/v1", tags=["benchmark"])
logger = logging.getLogger(__name__)

_run_store: dict[str, dict] = {}


@router.post("/benchmark/run", response_model=BenchmarkRunResponse)
def run_benchmark(request: BenchmarkRunRequest) -> BenchmarkRunResponse:
    run_id = benchmark_run_id()

    if request.dry_run:
        _run_store[run_id] = {"state": "accepted", "result": None}
        return BenchmarkRunResponse(
            status="accepted",
            run_id=run_id,
            suite_name=request.suite_name,
            accepted=True,
            message="dry-run benchmark accepted",
        )

    try:
        config = RunnerConfig(
            run_id=run_id,
            suite_name=request.suite_name or "all",
            case_ids=list(request.case_ids or []),
            keep_temp=request.metadata.get("keep_temp", False),
            ablation=request.metadata.get("ablation", False),
        )
        runner = BenchmarkRunner(config)
        result = runner.run()

        _run_store[run_id] = {
            "state": "completed",
            "result": to_json(result),
        }

        return BenchmarkRunResponse(
            status="completed",
            run_id=run_id,
            suite_name=request.suite_name,
            accepted=True,
            message=f"score={result.overall_score:.1f} rating={result.rating} passed={result.passed_cases}/{result.total_cases}",
        )
    except Exception as exc:
        logger.exception("Benchmark run %s failed", run_id)
        _run_store[run_id] = {"state": "failed", "result": None, "error": str(exc)}
        return BenchmarkRunResponse(
            status="failed",
            run_id=run_id,
            suite_name=request.suite_name,
            accepted=False,
            message=str(exc)[:200],
        )


@router.get("/benchmark/{run_id}", response_model=BenchmarkStatusResponse)
def get_benchmark_status(run_id: str) -> BenchmarkStatusResponse:
    entry = _run_store.get(run_id)
    if entry is None:
        return BenchmarkStatusResponse(
            status="ok",
            run_id=run_id,
            state="not_found",
            result=None,
            message="run_id not found",
        )
    return BenchmarkStatusResponse(
        status="ok",
        run_id=run_id,
        state=entry["state"],
        result=entry.get("result"),
        message="completed" if entry.get("result") else entry.get("error", ""),
    )
