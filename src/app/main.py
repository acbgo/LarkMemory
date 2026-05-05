from __future__ import annotations

import asyncio
import importlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.app.config import AppSettings
from src.app.dependencies import get_settings
from src.app.logging import RequestLogMiddleware, setup_logging


ROUTER_MODULES = [
    "src.api.health",
    "src.api.ingest",
    "src.api.retrieve",
    "src.api.embeddings",
    "src.api.rerank",
    "src.api.update",
    "src.api.proactive",
]

_REMINDER_TASK_ATTR = "_team_reminder_task"


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """创建 FastAPI 应用，输入可选 AppSettings，返回已注册中间件和路由的 app。"""
    resolved_settings = settings or get_settings()
    setup_logging(
        resolved_settings.log_level,
        resolved_settings.log_dir,
        resolved_settings.log_file,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        _start_reminder_loop(app)
        yield
        _stop_reminder_loop(app)

    app = FastAPI(
        title=resolved_settings.app_name,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    if resolved_settings.request_log_enabled:
        app.add_middleware(RequestLogMiddleware)

    register_routers(app)
    return app


def _start_reminder_loop(app: FastAPI) -> None:
    logger = logging.getLogger(__name__)
    try:
        from src.app.dependencies import (
            get_feishu_notifier,
            get_memory_service,
            get_team_retention_store,
        )
        from src.domains.team_retention.reminder_loop import TeamRetentionReminderLoop
        from src.sources.feishu.client.config import load_feishu_settings
    except ImportError:
        return

    feishu = load_feishu_settings()
    if not feishu.default_chat_id:
        return

    notifier = get_feishu_notifier()
    if notifier is None:
        return

    memory_service = get_memory_service()
    team_store = get_team_retention_store()

    loop = TeamRetentionReminderLoop(
        memory_service,
        notifier,
        team_store,
        chat_id=feishu.default_chat_id,
        interval_seconds=3600,
    )
    task = asyncio.create_task(loop.run())
    setattr(app.state, _REMINDER_TASK_ATTR, task)
    logger.info("action=reminder_loop_started chat_id=%s", feishu.default_chat_id)


def _stop_reminder_loop(app: FastAPI) -> None:
    logger = logging.getLogger(__name__)
    task = getattr(app.state, _REMINDER_TASK_ATTR, None)
    if task is not None:
        task.cancel()
        logger.info("action=reminder_loop_stopped")


def register_routers(app: FastAPI) -> list[str]:
    """按 ROUTER_MODULES 动态导入 API router 并注册到 app；返回成功注册的模块短名列表。"""
    logger = logging.getLogger(__name__)
    registered: list[str] = []
    for module_name in ROUTER_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name and (
                module_name == exc.name or module_name.startswith(f"{exc.name}.")
            ):
                continue
            raise

        router = getattr(module, "router", None)
        if router is None:
            logger.warning("API module %s has no router", module_name)
            continue

        app.include_router(router)
        registered.append(module_name.rsplit(".", 1)[-1])
    return registered

app = create_app()


def main() -> None:
    """读取运行配置并启动 Uvicorn 服务，作为命令行入口使用。"""
    settings = get_settings()
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Missing dependency: uvicorn") from exc
    uvicorn.run(
        "src.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
