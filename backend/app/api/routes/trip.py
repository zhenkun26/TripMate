"""行程规划与静态图代理路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.models.schemas import ApiEnvelope, TripPlan, TripPlanRequest
from app.services.container import Services
from app.services.errors import PlanRateLimitError, SharedPlanNotFoundError

router = APIRouter(prefix="/api/trip", tags=["trip"])


def _get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


def _get_client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


@router.post("/plan", response_model=ApiEnvelope[TripPlan])
async def create_trip_plan(
    request: TripPlanRequest,
    fastapi_request: Request,
) -> ApiEnvelope[TripPlan]:
    """生成旅行计划：限流 -> 真实数据采集 -> PlannerAgent 单次生成 -> 校验修复 -> 注入。"""
    services = _get_services(fastapi_request)
    # 该接口每次调用都消耗 LLM token，必须在最外层限流，防止单 IP 刷量
    if not await services.plan_rate_limiter.allow(_get_client_ip(fastapi_request)):
        raise PlanRateLimitError()
    collection = await services.collection_service.collect(
        city=request.city,
        preferences=request.preferences,
        accommodation=request.accommodation,
    )
    trip_plan = await services.planner_agent.plan(request, collection)
    # 签发分享 token（缓存不可用时为 None，前端隐藏分享链接入口，不影响主流程）
    trip_plan.share_token = await services.plan_store.save(trip_plan)
    return ApiEnvelope(code=0, data=trip_plan, message="success")


@router.get("/plan/{token}", response_model=ApiEnvelope[TripPlan])
async def get_shared_plan(token: str, request: Request) -> ApiEnvelope[TripPlan]:
    """按分享 token 取回行程（用于分享链接打开）；过期或篡改返回 404。"""
    services = _get_services(request)
    trip_plan = await services.plan_store.get(token)
    if trip_plan is None:
        raise SharedPlanNotFoundError()
    trip_plan.share_token = token
    return ApiEnvelope(code=0, data=trip_plan, message="success")


@router.get("/static-map/{token}")
async def get_static_map(token: str, request: Request) -> Response:
    """静态图代理：按不透明 token 取参渲染 PNG，命中缓存直接返回。"""
    services = _get_services(request)
    image_bytes = await services.static_map_service.render_map_image(
        token, _get_client_ip(request)
    )
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
