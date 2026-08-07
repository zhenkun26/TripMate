"""数据采集编排单元测试：三路并行、候选过滤、降级路径。"""

from __future__ import annotations

from datetime import UTC

import pytest

from app.services.cache_service import CacheService
from app.services.collection_service import (
    HOTEL_UNAVAILABLE_NOTICE,
    WEATHER_UNAVAILABLE_NOTICE,
    CollectionService,
)
from app.services.errors import AmapError
from app.services.poi_cache import PoiCache
from app.services.weather_cache import WeatherCache
from tests.conftest import FakeAmapClient, FakeCache, FakeClock


def make_raw_poi(
    poi_id: str,
    name: str,
    *,
    longitude: float = 116.3,
    latitude: float = 39.9,
    rating: str = "4.5",
    adcode: str = "110000",
) -> dict[str, object]:
    """构造高德原始 POI 响应条目。"""
    return {
        "id": poi_id,
        "name": name,
        "location": f"{longitude},{latitude}",
        "address": f"{name}地址",
        "type": "风景名胜;历史遗迹",
        "rating": rating,
        "adcode": adcode,
    }


def make_weather_payload() -> dict[str, object]:
    """构造高德天气响应。"""
    return {
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


def build_service(
    amap: FakeAmapClient,
    cache: CacheService | None = None,
) -> CollectionService:
    """装配带假缓存的采集服务。"""
    cache_service = cache or FakeCache()
    weather_cache = WeatherCache(cache_service, FakeClock())
    poi_cache = PoiCache(cache_service, FakeClock())
    return CollectionService(amap, cache_service, poi_cache, weather_cache)


@pytest.mark.asyncio
async def test_collect_should_return_real_candidates_and_weather(fake_amap: FakeAmapClient) -> None:
    fake_amap.attraction_pois = [make_raw_poi(f"A{i}", f"景点{i}", rating="4.6") for i in range(20)]
    fake_amap.hotel_pois = [make_raw_poi(f"H{i}", f"酒店{i}") for i in range(12)]
    fake_amap.weather_payload = make_weather_payload()
    service = build_service(fake_amap)

    result = await service.collect("北京", "历史文化", "舒适型酒店")

    assert result.adcode == "110000"
    assert len(result.attractions) == 15
    assert len(result.hotels) == 8
    assert len(result.weather) == 1
    assert result.weather[0].day_temp == 32
    assert result.notices == []


@pytest.mark.asyncio
async def test_collect_should_filter_low_rating_attractions(fake_amap: FakeAmapClient) -> None:
    fake_amap.attraction_pois = [
        make_raw_poi("A1", "高分景点", rating="4.8"),
        make_raw_poi("A2", "低分景点", rating="3.2"),
        make_raw_poi("A3", "无评分景点", rating=""),
    ]
    fake_amap.hotel_pois = [make_raw_poi("H1", "酒店1")]
    fake_amap.weather_payload = make_weather_payload()
    service = build_service(fake_amap)

    result = await service.collect("北京", "自然风光", "酒店")

    names = {item.name for item in result.attractions}
    assert names == {"高分景点", "无评分景点"}


@pytest.mark.asyncio
async def test_collect_should_raise_when_attractions_unavailable(fake_amap: FakeAmapClient) -> None:
    fake_amap.attraction_pois = [make_raw_poi("A1", "景点1")]
    fake_amap.fail_attraction_search = True
    service = build_service(fake_amap)
    with pytest.raises(AmapError, match="景点数据获取失败"):
        await service.collect("北京", "历史文化", "舒适型酒店")


@pytest.mark.asyncio
async def test_collect_should_degrade_when_hotel_search_fails(fake_amap: FakeAmapClient) -> None:
    fake_amap.attraction_pois = [make_raw_poi("A1", "景点1")]
    fake_amap.fail_hotel_search = True
    fake_amap.weather_payload = make_weather_payload()
    service = build_service(fake_amap)

    result = await service.collect("北京", "历史文化", "舒适型酒店")

    assert result.hotels == []
    assert HOTEL_UNAVAILABLE_NOTICE in result.notices


@pytest.mark.asyncio
async def test_collect_should_degrade_when_weather_unavailable(fake_amap: FakeAmapClient) -> None:
    fake_amap.attraction_pois = [make_raw_poi("A1", "景点1")]
    fake_amap.hotel_pois = [make_raw_poi("H1", "酒店1")]
    fake_amap.fail_weather = True
    service = build_service(fake_amap)

    result = await service.collect("北京", "历史文化", "舒适型酒店")

    assert result.weather == []
    assert WEATHER_UNAVAILABLE_NOTICE in result.notices


@pytest.mark.asyncio
async def test_collect_should_cache_adcode_and_reuse(fake_amap: FakeAmapClient) -> None:
    fake_amap.attraction_pois = [make_raw_poi("A1", "景点1")]
    fake_amap.hotel_pois = [make_raw_poi("H1", "酒店1")]
    fake_amap.weather_payload = make_weather_payload()
    cache = FakeCache()
    service = build_service(fake_amap, cache)

    await service.collect("北京", "历史文化", "舒适型酒店")
    first_call_count = len(fake_amap.search_calls)
    await service.collect("北京", "历史文化", "舒适型酒店")

    assert len(fake_amap.search_calls) == first_call_count
    assert await cache.get("tripmate:cityadcode:北京") == "110000"


@pytest.mark.asyncio
async def test_collect_should_include_weather_updated_at(fake_amap: FakeAmapClient) -> None:
    fake_amap.attraction_pois = [make_raw_poi("A1", "景点1")]
    fake_amap.hotel_pois = [make_raw_poi("H1", "酒店1")]
    fake_amap.weather_payload = make_weather_payload()
    service = build_service(fake_amap)

    result = await service.collect("北京", "历史文化", "舒适型酒店")

    assert result.weather_updated_at is not None
    assert result.weather_updated_at.tzinfo == UTC
