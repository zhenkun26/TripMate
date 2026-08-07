"""FastAPI 应用入口与统一错误处理。"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, Response
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
from app.services.plan_store import PlanStore
from app.services.poi_cache import PoiCache
from app.services.rate_limit import create_rate_limiter
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
            rate_limiter=create_rate_limiter(
                cache_service,
                key_prefix="tripmate:rl:staticmap:",
                max_requests=app_settings.static_map_rate_limit_per_minute,
            ),
        )
        planner_agent = PlannerAgent(llm_client, static_map_service)
        plan_rate_limiter = create_rate_limiter(
            cache_service,
            key_prefix="tripmate:rl:plan:",
            max_requests=app_settings.plan_rate_limit_per_minute,
        )
        app.state.services = Services(
            cache_service=cache_service,
            amap_client=amap_client,
            weather_cache=weather_cache,
            poi_cache=poi_cache,
            collection_service=collection_service,
            static_map_service=static_map_service,
            llm_client=llm_client,
            planner_agent=planner_agent,
            plan_rate_limiter=plan_rate_limiter,
            plan_store=PlanStore(
                cache_service,
                ttl_seconds=app_settings.plan_share_ttl_seconds,
            ),
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

    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable[..., Any]) -> Response:
        """请求日志中间件：生成/透传 request id，记录方法、路径、状态码与耗时。"""
        request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
        started_at = time.perf_counter()
        response: Response = await call_next(request)
        latency_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "%s %s -> %s (%.0fms) rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
            request_id,
        )
        response.headers["X-Request-ID"] = request_id
        return response

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
