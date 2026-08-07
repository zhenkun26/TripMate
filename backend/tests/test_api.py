"""API 集成测试：happy path、参数校验、LLM 失败、静态图缓存与防篡改。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.llm_client import LLMClient
from app.agents.planner_agent import PlannerAgent
from app.api.main import create_app
from app.config.settings import Settings
from app.models.schemas import TripPlan, TripPlanRequest
from app.services.collection_service import CollectionService
from app.services.container import Services
from app.services.errors import LLMOutputError
from app.services.plan_store import PlanStore
from app.services.poi_cache import PoiCache
from app.services.rate_limit import SlidingWindowRateLimiter
from app.services.static_map_service import StaticMapService
from app.services.weather_cache import WeatherCache
from tests.conftest import FakeAmapClient, FakeCache, FakeClock, make_request, make_trip_plan


class FakePlanner:
    """可编排结果的假 Planner。"""

    def __init__(self, trip_plan: TripPlan | None = None, error: Exception | None = None) -> None:
        self.trip_plan = trip_plan or make_trip_plan()
        self.error = error

    async def plan(self, request: TripPlanRequest, collection: Any) -> TripPlan:
        if self.error is not None:
            raise self.error
        return self.trip_plan


@contextmanager
def build_client(planner: FakePlanner | None = None) -> Iterator[tuple[TestClient, FakeAmapClient]]:
    """构造带假服务的 TestClient，产出 (client, amap)。"""
    app = create_app(
        Settings(
            redis_url="redis://127.0.0.1:1/0",
            amap_api_key="",
            llm_api_key="",
            llm_base_url="https://llm.example.com",
        )
    )
    with TestClient(app) as client:
        cache = FakeCache()
        amap = FakeAmapClient()
        amap.attraction_pois = [
            {
                "id": f"POI-{index}",
                "name": f"景点{index}",
                "location": f"{116.3 + index / 10},39.9",
                "address": f"地址{index}",
                "type": "风景名胜",
                "rating": "4.6",
                "adcode": "110000",
            }
            for index in range(6)
        ]
        amap.hotel_pois = [
            {
                "id": f"HOTEL-{index}",
                "name": f"酒店{index}",
                "location": "116.4,39.9",
                "address": f"酒店地址{index}",
                "type": "酒店",
                "rating": "4.5",
                "biz_ext": {"cost": "500"},
            }
            for index in range(3)
        ]
        amap.weather_payload = {
            "status": "1",
            "lives": [],
            "forecasts": [
                {
                    "casts": [
                        {
                            "date": "2026-08-07",
                            "dayweather": "晴",
                            "nightweather": "多云",
                            "daytemp": "32℃",
                            "nighttemp": "24℃",
                            "daywind": "东南风",
                            "daypower": "3级",
                        }
                    ]
                }
            ],
        }
        weather_cache = WeatherCache(cache, FakeClock())
        poi_cache = PoiCache(cache, FakeClock())
        collection_service = CollectionService(amap, cache, poi_cache, weather_cache)
        static_map_service = StaticMapService(
            cache,
            amap,
            size="750x400",
            token_ttl_seconds=86400,
            rate_limiter=SlidingWindowRateLimiter(60),
        )
        cast(FastAPI, client.app).state.services = Services(
            cache_service=cache,
            amap_client=amap,
            weather_cache=weather_cache,
            poi_cache=poi_cache,
            collection_service=collection_service,
            static_map_service=static_map_service,
            llm_client=LLMClient(
                base_url="https://llm.example.com",
                api_key="",
                model="fake-model",
            ),
            planner_agent=cast(PlannerAgent, planner or FakePlanner()),
            plan_rate_limiter=SlidingWindowRateLimiter(1000),
            plan_store=PlanStore(cache, ttl_seconds=3600),
        )
        yield client, amap


@pytest.fixture
def plan_payload() -> dict[str, Any]:
    """合法的规划请求体。"""
    return make_request().model_dump(mode="json")


def test_should_return_plan_envelope_on_happy_path(plan_payload: dict[str, Any]) -> None:
    with build_client() as (client, _amap):
        response = client.post("/api/trip/plan", json=plan_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["message"] == "success"
        assert len(body["data"]["days"]) == 3
        assert body["data"]["map_image_url"].startswith("/api/trip/static-map/")


def test_should_return_422_when_required_field_missing(plan_payload: dict[str, Any]) -> None:
    with build_client() as (client, _amap):
        plan_payload.pop("city")
        response = client.post("/api/trip/plan", json=plan_payload)
        assert response.status_code == 422
        assert "请求参数校验失败" in response.json()["message"]


def test_should_return_422_when_days_mismatch_date_range(plan_payload: dict[str, Any]) -> None:
    with build_client() as (client, _amap):
        plan_payload["days"] = 2
        response = client.post("/api/trip/plan", json=plan_payload)
        assert response.status_code == 422
        assert "不一致" in response.json()["message"]


def test_should_return_502_when_llm_fails_after_retries(plan_payload: dict[str, Any]) -> None:
    failing_planner = FakePlanner(error=LLMOutputError("生成计划失败，请稍后重试"))
    with build_client(failing_planner) as (client, _amap):
        response = client.post("/api/trip/plan", json=plan_payload)
        assert response.status_code == 502
        assert response.json()["message"] == "生成计划失败，请稍后重试"


def test_should_return_429_when_plan_rate_limited(plan_payload: dict[str, Any]) -> None:
    with build_client() as (client, _amap):
        app = cast(FastAPI, client.app)
        app.state.services.plan_rate_limiter = SlidingWindowRateLimiter(1)
        first_response = client.post("/api/trip/plan", json=plan_payload)
        second_response = client.post("/api/trip/plan", json=plan_payload)
        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert "频繁" in second_response.json()["message"]


def test_should_return_502_when_amap_unavailable(plan_payload: dict[str, Any]) -> None:
    with build_client() as (client, amap):
        amap.fail_attraction_search = True
        response = client.post("/api/trip/plan", json=plan_payload)
        assert response.status_code == 502
        assert "景点数据获取失败" in response.json()["message"]


def test_should_serve_static_map_and_cache_image() -> None:
    with build_client() as (client, amap):
        app = cast(FastAPI, client.app)
        planner = cast(FakePlanner, app.state.services.planner_agent)
        static_map_service = app.state.services.static_map_service
        token = asyncio.run(static_map_service.create_map_token(planner.trip_plan))
        assert token is not None

        first_response = client.get(f"/api/trip/static-map/{token}")
        second_response = client.get(f"/api/trip/static-map/{token}")

        assert first_response.status_code == 200
        assert first_response.headers["content-type"] == "image/png"
        assert first_response.content == b"\x89PNG\r\n\x1a\nfake-static-map"
        assert second_response.status_code == 200
        assert amap.static_map_calls == 1


def test_should_return_404_for_forged_static_map_token() -> None:
    with build_client() as (client, _amap):
        response = client.get("/api/trip/static-map/forged-token")
        assert response.status_code == 404
        assert response.json()["message"] == "地图资源不存在或已过期"


def test_should_issue_share_token_and_serve_shared_plan(plan_payload: dict[str, Any]) -> None:
    with build_client() as (client, _amap):
        create_response = client.post("/api/trip/plan", json=plan_payload)
        assert create_response.status_code == 200
        share_token = create_response.json()["data"]["share_token"]
        assert share_token

        shared_response = client.get(f"/api/trip/plan/{share_token}")
        assert shared_response.status_code == 200
        assert shared_response.json()["data"]["city"] == "北京"
        assert shared_response.json()["data"]["share_token"] == share_token


def test_should_return_404_for_forged_share_token() -> None:
    with build_client() as (client, _amap):
        response = client.get("/api/trip/plan/forged-token")
        assert response.status_code == 404
        assert "分享行程" in response.json()["message"]


def test_health_check_should_report_status() -> None:
    with build_client() as (client, _amap):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ok"
