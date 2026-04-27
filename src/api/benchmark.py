from __future__ import annotations

import uuid

from fastapi import APIRouter

from src.schemas import (
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BenchmarkStatusResponse,
)


router = APIRouter(prefix="/api/v1", tags=["benchmark"])


def _new_run_id() -> str:
    return f"bench-{uuid.uuid4().hex[:12]}"


@router.post("/benchmark/run", response_model=BenchmarkRunResponse)
def run_benchmark(request: BenchmarkRunRequest) -> BenchmarkRunResponse:
    if request.dry_run:
        return BenchmarkRunResponse(
            status="accepted",
            run_id=_new_run_id(),
            suite_name=request.suite_name,
            accepted=True,
            message="dry-run benchmark accepted",
        )
    return BenchmarkRunResponse(
        status="not_implemented",
        run_id=_new_run_id(),
        suite_name=request.suite_name,
        accepted=False,
        message="benchmark runner not implemented",
    )


@router.get("/benchmark/{run_id}", response_model=BenchmarkStatusResponse)
def get_benchmark_status(run_id: str) -> BenchmarkStatusResponse:
    return BenchmarkStatusResponse(
        status="ok",
        run_id=run_id,
        state="not_found",
        result=None,
        message="benchmark runner not implemented",
    )
