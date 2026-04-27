from __future__ import annotations

from fastapi import APIRouter

from src.schemas import (
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BenchmarkStatusResponse,
)
from src.utils.ids import benchmark_run_id


router = APIRouter(prefix="/api/v1", tags=["benchmark"])


@router.post("/benchmark/run", response_model=BenchmarkRunResponse)
def run_benchmark(request: BenchmarkRunRequest) -> BenchmarkRunResponse:
    """接收评测请求并返回受理状态。"""
    if request.dry_run:
        return BenchmarkRunResponse(
            status="accepted",
            run_id=benchmark_run_id(),
            suite_name=request.suite_name,
            accepted=True,
            message="dry-run benchmark accepted",
        )
    return BenchmarkRunResponse(
        status="not_implemented",
        run_id=benchmark_run_id(),
        suite_name=request.suite_name,
        accepted=False,
        message="benchmark runner not implemented",
    )


@router.get("/benchmark/{run_id}", response_model=BenchmarkStatusResponse)
def get_benchmark_status(run_id: str) -> BenchmarkStatusResponse:
    """查询评测任务状态并返回当前结果。"""
    return BenchmarkStatusResponse(
        status="ok",
        run_id=run_id,
        state="not_found",
        result=None,
        message="benchmark runner not implemented",
    )
