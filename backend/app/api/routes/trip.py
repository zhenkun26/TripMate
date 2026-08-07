"""行程规划与静态图代理路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.models.schemas import ApiEnvelope, TripPlan, TripPlanRequest
from app.services.container import Services

router = APIRouter(prefix="/api/trip", tags=["trip"])


def _get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


@router.post("/plan", response_model=ApiEnvelope[TripPlan])
async def create_trip_plan(
    request: TripPlanRequest,
    fastapi_request: Request,
) -> ApiEnvelope[TripPlan]:
    """生成旅行计划：真实数据采集 -> PlannerAgent 单次生成 -> 校验修复 -> 预算/天气/地图注入。"""
    services = _get_services(fastapi_request)
    collection = await services.collection_service.collect(
        city=request.city,
        preferences=request.preferences,
        accommodation=request.accommodation,
    )
    trip_plan = await services.planner_agent.plan(request, collection)
    return ApiEnvelope(code=0, data=trip_plan, message="success")


@router.get("/static-map/{token}")
async def get_static_map(token: str, request: Request) -> Response:
    """静态图代理：按不透明 token 取参渲染 PNG，命中缓存直接返回。"""
    services = _get_services(request)
    client_ip = request.client.host if request.client is not None else "unknown"
    image_bytes = await services.static_map_service.render_map_image(token, client_ip)
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
