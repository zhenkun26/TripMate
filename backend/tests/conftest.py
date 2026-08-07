"""共享测试夹具：FakeCache / FakeClock / FakeAmapClient / 样例数据。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.models.schemas import (
    Attraction,
    Budget,
    DayPlan,
    Hotel,
    Location,
    TripPlan,
    TripPlanDraft,
    TripPlanRequest,
    WeatherInfo,
)
from app.services.amap_client import AmapClient
from app.services.cache_service import CacheService


class FakeCache(CacheService):
    """内存缓存实现，available 可切换以模拟 Redis 故障。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._available = True
        self.set_calls: list[tuple[str, str, int]] = []

    async def ping(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    @available.setter
    def available(self, value: bool) -> None:
        self._available = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = value
        self.set_calls.append((key, value, ttl_seconds))

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class FakeClock:
    """可手动推进的时钟。"""

    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 8, 7, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class FakeAmapClient(AmapClient):
    """内存版高德客户端：可配置 POI/天气/静态图响应与失败模式。"""

    def __init__(self) -> None:
        super().__init__(
            api_key="test-key",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        )
        self.attraction_pois: list[dict[str, object]] = []
        self.hotel_pois: list[dict[str, object]] = []
        self.weather_payload: dict[str, object] = {}
        self.static_map_bytes = b"\x89PNG\r\n\x1a\nfake-static-map"
        self.search_calls: list[tuple[str, list[str]]] = []
        self.static_map_calls = 0
        self.fail_city_search = False
        self.fail_attraction_search = False
        self.fail_hotel_search = False
        self.fail_weather = False

    async def search_pois(self, city: str, keywords: list[str]) -> list[dict[str, Any]]:
        self.search_calls.append((city, keywords))
        if keywords == [city]:
            if self.fail_city_search:
                raise httpx.TransportError("city search failed")
            return self.attraction_pois
        joined_keywords = "|".join(keywords)
        if "酒店" in joined_keywords:
            if self.fail_hotel_search:
                raise httpx.TransportError("hotel search failed")
            return self.hotel_pois
        if self.fail_attraction_search:
            raise httpx.TransportError("attraction search failed")
        return self.attraction_pois

    async def get_weather(self, adcode: str) -> dict[str, Any]:
        if self.fail_weather:
            raise httpx.TransportError("weather failed")
        return self.weather_payload

    async def fetch_static_map(self, params: dict[str, str]) -> bytes:
        self.static_map_calls += 1
        return self.static_map_bytes


def make_location(longitude: float = 116.397, latitude: float = 39.909) -> Location:
    """构造样例坐标。"""
    return Location(longitude=longitude, latitude=latitude)


def make_attraction(
    *,
    name: str = "故宫",
    poi_id: str = "B000A70VOO",
    longitude: float = 116.397,
    latitude: float = 39.909,
    ticket_price: int = 60,
    rating: float = 4.8,
) -> Attraction:
    """构造样例景点。"""
    return Attraction(
        name=name,
        address="北京市东城区",
        location=make_location(longitude, latitude),
        visit_duration=120,
        description="明清皇家宫殿",
        category="历史遗迹",
        rating=rating,
        ticket_price=ticket_price,
        poi_id=poi_id,
    )


def make_hotel(
    *,
    name: str = "北京王府井酒店",
    poi_id: str = "B000A7HJKL",
    estimated_cost: int = 500,
) -> Hotel:
    """构造样例酒店。"""
    return Hotel(
        name=name,
        address="北京市东城区王府井",
        location=make_location(116.41, 39.91),
        price_range="约500元/晚",
        rating="4.6",
        distance="1.2km",
        type="舒适型酒店",
        estimated_cost=estimated_cost,
        poi_id=poi_id,
    )


def make_weather(date: str = "2026-08-07", day_temp: int = 32) -> WeatherInfo:
    """构造样例天气。"""
    return WeatherInfo(
        date=date,
        day_weather="晴",
        night_weather="多云",
        day_temp=day_temp,
        night_temp=24,
        wind_direction="东南风",
        wind_power="3级",
    )


def make_request(
    *,
    city: str = "北京",
    start_date: str = "2026-08-07",
    days: int = 3,
    preferences: str = "历史文化",
    budget: str = "舒适型",
    transportation: str = "公共交通",
    accommodation: str = "舒适型酒店",
) -> TripPlanRequest:
    """构造样例规划请求。"""
    start = datetime.fromisoformat(start_date).date()
    end = start + timedelta(days=days - 1)
    return TripPlanRequest(
        city=city,
        start_date=start,
        end_date=end,
        days=days,
        preferences=preferences,
        budget=budget,
        transportation=transportation,
        accommodation=accommodation,
    )


def make_draft(
    *,
    days_count: int = 3,
    city: str = "北京",
    start_date: str = "2026-08-07",
) -> TripPlanDraft:
    """构造通过校验的样例行程草稿。"""
    start = datetime.fromisoformat(start_date).date()
    day_plans: list[DayPlan] = []
    for day_index in range(days_count):
        day_date = start + timedelta(days=day_index)
        day_plans.append(
            DayPlan(
                date=day_date.isoformat(),
                day_index=day_index,
                description=f"第{day_index + 1}天行程",
                transportation="公共交通",
                accommodation="市区酒店",
                hotel=make_hotel(name="酒店0", poi_id="HOTEL-0") if day_index == 0 else None,
                attractions=[
                    make_attraction(
                        name=f"景点{day_index}A",
                        poi_id=f"POI-{day_index}-A",
                        longitude=116.3 + day_index,
                        latitude=39.9 + day_index * 0.1,
                        ticket_price=50,
                    ),
                    make_attraction(
                        name=f"景点{day_index}B",
                        poi_id=f"POI-{day_index}-B",
                        longitude=116.4 + day_index,
                        latitude=40.0 + day_index * 0.1,
                        ticket_price=30,
                    ),
                ],
            )
        )
    return TripPlanDraft(
        city=city,
        start_date=start_date,
        end_date=(start + timedelta(days=days_count - 1)).isoformat(),
        days=day_plans,
        overall_suggestions="建议早出发；穿舒适鞋；提前订票",
        budget=Budget(
            total_attractions=160,
            total_hotels=500,
            total_transportation=300,
            total=960,
        ),
    )


def make_trip_plan(*, with_map: bool = True) -> TripPlan:
    """构造样例 TripPlan（含派生字段）。"""
    draft = make_draft()
    trip_plan = TripPlan(
        **draft.model_dump(),
        weather_info=[make_weather()],
        weather_updated_at="2026-08-07T08:00:00+00:00",
        weather_stale=False,
        map_image_url="/api/trip/static-map/token123" if with_map else None,
        notices=[],
    )
    return trip_plan


@pytest.fixture
def fake_cache() -> FakeCache:
    """内存缓存夹具。"""
    return FakeCache()


@pytest.fixture
def fake_amap() -> FakeAmapClient:
    """内存高德客户端夹具。"""
    return FakeAmapClient()
