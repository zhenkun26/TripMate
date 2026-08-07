"""缓存单元测试：命中/过期/宽限/绕过降级/并发单飞。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.models.schemas import WeatherInfo
from app.services.cache_service import NullCacheService, RedisCacheService, create_cache_service
from app.services.errors import WeatherUnavailableError
from app.services.poi_cache import PoiCache
from app.services.weather_cache import WEATHER_FRESH_TTL, WEATHER_GRACE_EXTRA, WeatherCache
from tests.conftest import FakeCache, FakeClock, make_weather


async def should_not_be_called() -> list[WeatherInfo]:
    """标记不应被触发的 fetch 回调。"""
    raise AssertionError("不应触发抓取")


async def should_not_fetch_pois() -> list[dict[str, object]]:
    """标记不应被触发的 POI fetch 回调。"""
    raise AssertionError("不应触发抓取")


@pytest.mark.asyncio
async def test_should_return_none_from_null_cache() -> None:
    cache = NullCacheService()
    assert not cache.available
    assert await cache.get("any-key") is None
    await cache.set("any-key", "value", 60)
    await cache.delete("any-key")


@pytest.mark.asyncio
async def test_should_fallback_to_null_cache_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_cache = RedisCacheService("redis://127.0.0.1:1/0")

    class FailingRedis:
        async def ping(self) -> None:
            raise RedisConnectionError("connection refused")

    monkeypatch.setattr(redis_cache, "_redis", FailingRedis())
    cache_service = await create_cache_service("redis://127.0.0.1:1/0")
    assert isinstance(cache_service, NullCacheService)


@pytest.mark.asyncio
async def test_weather_cache_should_hit_fresh_entry() -> None:
    cache = FakeCache()
    clock = FakeClock()
    weather_cache = WeatherCache(cache, clock)
    weather = [make_weather()]
    await weather_cache._write_entry(weather_cache.build_key("110000"), weather, clock())

    result, fetched_at, stale = await weather_cache.get_or_refresh(
        "110000",
        should_not_be_called,
    )
    assert result == weather
    assert not stale
    assert fetched_at == clock()


@pytest.mark.asyncio
async def test_weather_cache_should_serve_stale_within_grace() -> None:
    cache = FakeCache()
    clock = FakeClock()
    weather_cache = WeatherCache(cache, clock)
    weather = [make_weather()]
    await weather_cache._write_entry(weather_cache.build_key("110000"), weather, clock())
    clock.advance(WEATHER_FRESH_TTL + timedelta(hours=1))

    result, _fetched_at, stale = await weather_cache.get_or_refresh(
        "110000",
        should_not_be_called,
    )
    assert result == weather
    assert stale


@pytest.mark.asyncio
async def test_weather_cache_should_refresh_when_expired() -> None:
    cache = FakeCache()
    clock = FakeClock()
    weather_cache = WeatherCache(cache, clock)
    old_weather = [make_weather(day_temp=20)]
    await weather_cache._write_entry(weather_cache.build_key("110000"), old_weather, clock())
    clock.advance(WEATHER_FRESH_TTL + WEATHER_GRACE_EXTRA + timedelta(minutes=1))

    async def fetch() -> list[WeatherInfo]:
        return [make_weather(day_temp=35)]

    result, _fetched_at, stale = await weather_cache.get_or_refresh("110000", fetch)
    assert result[0].day_temp == 35
    assert not stale


@pytest.mark.asyncio
async def test_weather_cache_should_return_stale_when_refresh_fails_and_old_exists() -> None:
    cache = FakeCache()
    clock = FakeClock()
    weather_cache = WeatherCache(cache, clock)
    old_weather = [make_weather()]
    await weather_cache._write_entry(weather_cache.build_key("110000"), old_weather, clock())
    clock.advance(WEATHER_FRESH_TTL + WEATHER_GRACE_EXTRA + timedelta(minutes=1))

    async def failing_fetch() -> list[WeatherInfo]:
        raise ConnectionError("network down")

    result, _fetched_at, stale = await weather_cache.get_or_refresh("110000", failing_fetch)
    assert result == old_weather
    assert stale


@pytest.mark.asyncio
async def test_weather_cache_should_raise_when_no_cache_and_fetch_fails() -> None:
    cache = FakeCache()
    weather_cache = WeatherCache(cache, FakeClock())

    async def failing_fetch() -> list[WeatherInfo]:
        raise ConnectionError("network down")

    with pytest.raises(WeatherUnavailableError):
        await weather_cache.get_or_refresh("110000", failing_fetch)


@pytest.mark.asyncio
async def test_weather_cache_single_flight_concurrent_requests() -> None:
    cache = FakeCache()
    weather_cache = WeatherCache(cache, FakeClock())
    fetch_calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_fetch() -> list[WeatherInfo]:
        nonlocal fetch_calls
        fetch_calls += 1
        started.set()
        await release.wait()
        return [make_weather()]

    first_task = asyncio.create_task(weather_cache.get_or_refresh("110000", slow_fetch))
    await started.wait()
    second_task = asyncio.create_task(weather_cache.get_or_refresh("110000", slow_fetch))
    release.set()
    await asyncio.gather(first_task, second_task)
    assert fetch_calls == 1


@pytest.mark.asyncio
async def test_poi_cache_should_hit_fresh_entry() -> None:
    cache = FakeCache()
    clock = FakeClock()
    poi_cache = PoiCache(cache, clock)
    key = poi_cache.build_key("110000", "attraction", ["博物馆"])
    cached_payload = f'{{"fetched_at": "{clock().isoformat()}", "pois": [{{"id": "P1"}}]}}'
    await cache.set(key, cached_payload, 999)

    pois, stale = await poi_cache.get_or_fetch(
        "110000",
        "attraction",
        ["博物馆"],
        should_not_fetch_pois,
    )
    assert pois == [{"id": "P1"}]
    assert not stale


@pytest.mark.asyncio
async def test_poi_cache_should_return_stale_within_grace() -> None:
    cache = FakeCache()
    clock = FakeClock()
    poi_cache = PoiCache(cache, clock)
    key = poi_cache.build_key("110000", "attraction", ["博物馆"])
    cached_payload = f'{{"fetched_at": "{clock().isoformat()}", "pois": [{{"id": "P1"}}]}}'
    await cache.set(key, cached_payload, 999)
    clock.advance(timedelta(hours=49))

    pois, stale = await poi_cache.get_or_fetch(
        "110000",
        "attraction",
        ["博物馆"],
        should_not_fetch_pois,
    )
    assert pois == [{"id": "P1"}]
    assert stale


@pytest.mark.asyncio
async def test_poi_cache_should_cache_empty_result_with_short_ttl() -> None:
    cache = FakeCache()
    poi_cache = PoiCache(cache, FakeClock())
    fetch_calls = 0

    async def empty_fetch() -> list[dict[str, object]]:
        nonlocal fetch_calls
        fetch_calls += 1
        return []

    await poi_cache.get_or_fetch("110000", "attraction", ["景点"], empty_fetch)
    await poi_cache.get_or_fetch("110000", "attraction", ["景点"], empty_fetch)
    assert fetch_calls == 1
    assert cache.set_calls[-1][2] == 30 * 60
