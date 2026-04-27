from __future__ import annotations

import importlib
import logging

from fastapi import FastAPI

from src.app.config import AppSettings
from src.app.dependencies import get_settings
from src.app.logging import RequestLogMiddleware, setup_logging


ROUTER_MODULES = [
    "src.api.health",
    "src.api.ingest",
    "src.api.retrieve",
    "src.api.update",
    "src.api.proactive",
    "src.api.benchmark",
]


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """创建 FastAPI 应用，输入可选 AppSettings，返回已注册中间件和路由的 app。"""
    resolved_settings = settings or get_settings()
    setup_logging(
        resolved_settings.log_level,
        resolved_settings.log_dir,
        resolved_settings.log_file,
    )

    app = FastAPI(title=resolved_settings.app_name, debug=resolved_settings.debug)
    app.state.settings = resolved_settings

    if resolved_settings.request_log_enabled:
        app.add_middleware(RequestLogMiddleware)

    register_routers(app)
    return app


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
