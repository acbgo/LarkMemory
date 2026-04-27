from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BenchmarkRunRequest(BaseModel):
    suite_name: str = "default"
    case_ids: list[str] = Field(default_factory=list)
    dry_run: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkRunResponse(BaseModel):
    status: str
    run_id: str
    suite_name: str
    accepted: bool
    message: str | None = None


class BenchmarkStatusResponse(BaseModel):
    status: str
    run_id: str
    state: str
    result: dict[str, Any] | None = None
    message: str | None = None
