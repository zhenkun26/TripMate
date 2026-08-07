"""FastAPI 应用入口与统一错误处理。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.llm_client import LLMClient
from app.agents.planner_agent import PlannerAgent
from app.api.routes.trip import router as trip_router
from app.config.settings import Settings, get_settings
from app.models.schemas import ApiEnvelope
from app.services.amap_client import AmapClient
from app.services.cache_service import create_cache_service
from app.services.collection_service import CollectionService
from app.services.container import Services
from app.services.errors import TripMateError
from app.services.poi_cache import PoiCache
from app.services.static_map_service import StaticMapService
from app.services.weather_cache import WeatherCache

logger = logging.getLogger(__name__)


def _error_envelope(code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "data": None, "message": message},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """构建 FastAPI 应用（settings 可注入以便测试）。"""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cache_service = await create_cache_service(app_settings.redis_url)
        amap_client = AmapClient(app_settings.amap_api_key)
        weather_cache = WeatherCache(cache_service)
        poi_cache = PoiCache(cache_service)
        collection_service = CollectionService(amap_client, cache_service, poi_cache, weather_cache)
        llm_client = LLMClient(
            base_url=app_settings.llm_base_url,
            api_key=app_settings.llm_api_key,
            model=app_settings.llm_model,
            temperature=app_settings.llm_temperature,
            timeout_seconds=app_settings.llm_timeout_seconds,
        )
        static_map_service = StaticMapService(
            cache_service,
            amap_client,
            size=app_settings.static_map_size,
            token_ttl_seconds=app_settings.static_map_token_ttl_seconds,
            rate_limit_per_minute=app_settings.static_map_rate_limit_per_minute,
        )
        planner_agent = PlannerAgent(llm_client, static_map_service)
        app.state.services = Services(
            cache_service=cache_service,
            amap_client=amap_client,
            weather_cache=weather_cache,
            poi_cache=poi_cache,
            collection_service=collection_service,
            static_map_service=static_map_service,
            llm_client=llm_client,
            planner_agent=planner_agent,
        )
        yield
        await amap_client.aclose()

    app = FastAPI(title="TripMate API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(trip_router)

    @app.get("/api/health")
    async def health_check(request: Request) -> ApiEnvelope[dict[str, Any]]:
        """健康检查：返回 Redis 可用状态。"""
        services: Services = request.app.state.services
        redis_available = await services.cache_service.ping()
        return ApiEnvelope(
            code=0,
            data={"status": "ok", "redis": redis_available},
            message="success",
        )

    @app.exception_handler(TripMateError)
    async def handle_tripmate_error(request: Request, exc: TripMateError) -> JSONResponse:
        logger.error("业务错误 [%s] %s", exc.status_code, exc.message)
        return _error_envelope(exc.status_code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        first_error = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in first_error.get("loc", []))
        message = f"请求参数校验失败: {field} {first_error.get('msg', '')}".strip()
        return _error_envelope(422, message)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_envelope(int(exc.status_code), str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return _error_envelope(500, "服务器内部错误")

    return app


app = create_app()
