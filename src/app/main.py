from __future__ import annotations

import asyncio
import importlib
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.app.config import AppSettings
from src.app.dependencies import get_memory_service, get_settings
from src.app.logging import RequestLogMiddleware, setup_logging
from src.sources.feishu.client.config import load_feishu_settings
from src.sources.feishu.client.doc_client import FeishuDocClient
from src.sources.feishu.client.listener import build_event_handler
from src.sources.feishu.client.sdk import build_api_client, build_ws_client
from src.sources.feishu.client.vc_client import FeishuVcClient
from src.storage.source_state_store import SourceStateStore


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
_FEISHU_WS_THREAD_ATTR = "_feishu_ws_thread"
_FEISHU_WS_CLIENT_ATTR = "_feishu_ws_client"


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
        _start_feishu_ws_listener(app)
        _start_reminder_loop(app)
        yield
        _stop_reminder_loop(app)
        _stop_feishu_ws_listener(app)

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


def _start_feishu_ws_listener(app: FastAPI) -> None:
    """按配置在后台线程启动飞书 WebSocket listener，不阻塞 FastAPI 主服务。"""
    logger = logging.getLogger(__name__)

    try:
        feishu_settings = load_feishu_settings()
    except Exception:
        logger.warning("action=feishu_ws_settings_failed", exc_info=True)
        return
    if not feishu_settings.enable_ws:
        logger.info("action=feishu_ws_skipped reason=disabled")
        return

    try:
        api_client = build_api_client(feishu_settings)
        source_state_store = SourceStateStore()
        source_state_store.create_table()
        handler = build_event_handler(
            memory_service=get_memory_service(),
            settings=feishu_settings,
            source_state_store=source_state_store,
            vc_client=FeishuVcClient(api_client),
            doc_client=FeishuDocClient(api_client),
        )
        client = build_ws_client(feishu_settings, handler)
        setattr(app.state, _FEISHU_WS_CLIENT_ATTR, client)
    except Exception:
        logger.warning("action=feishu_ws_listener_init_failed", exc_info=True)
        return

    def run_listener() -> None:
        try:
            logger.info("action=feishu_ws_listener_started")
            client.start()
        except Exception:
            logger.warning("action=feishu_ws_listener_failed", exc_info=True)

    thread = threading.Thread(
        target=run_listener,
        name="feishu-ws-listener",
        daemon=True,
    )
    setattr(app.state, _FEISHU_WS_THREAD_ATTR, thread)
    thread.start()


def _stop_feishu_ws_listener(app: FastAPI) -> None:
    """关闭飞书 WebSocket client；SDK 无显式关闭 API 时依赖 daemon thread 随进程退出。"""
    logger = logging.getLogger(__name__)
    client = getattr(app.state, _FEISHU_WS_CLIENT_ATTR, None)
    close = None
    if client is not None:
        close = getattr(client, "close", None) or getattr(client, "stop", None)
    if callable(close):
        try:
            close()
        except Exception:
            logger.warning("action=feishu_ws_listener_close_failed", exc_info=True)

    thread = getattr(app.state, _FEISHU_WS_THREAD_ATTR, None)
    if thread is not None and thread.is_alive():
        thread.join(timeout=5)
    logger.info("action=feishu_ws_listener_stopped")


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
