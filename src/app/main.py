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
    resolved_settings = settings or get_settings()
    setup_logging(resolved_settings.log_level)

    app = FastAPI(title=resolved_settings.app_name, debug=resolved_settings.debug)
    app.state.settings = resolved_settings

    if resolved_settings.request_log_enabled:
        app.add_middleware(RequestLogMiddleware)

    register_routers(app)
    if not has_route(app, "/health", "GET"):
        register_builtin_health_route(app)
    return app


def register_routers(app: FastAPI) -> list[str]:
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


def register_builtin_health_route(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict[str, object]:
        settings: AppSettings = app.state.settings
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.env,
            "llm_enabled": settings.enable_llm,
            "embedding_enabled": settings.enable_embedding,
        }


def has_route(app: FastAPI, path: str, method: str) -> bool:
    expected_method = method.upper()
    for route in app.routes:
        route_path = getattr(route, "path", None)
        route_methods = getattr(route, "methods", set()) or set()
        if route_path == path and expected_method in route_methods:
            return True
    return False


app = create_app()


def main() -> None:
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
