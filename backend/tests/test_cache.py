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


class FlappingRedis:
    """先连接失败、可手动恢复的假 Redis。"""

    def __init__(self) -> None:
        self.healthy = False
        self.store: dict[str, str] = {}

    async def ping(self) -> bool:
        if not self.healthy:
            raise RedisConnectionError("connection refused")
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.mark.asyncio
async def test_create_cache_service_should_keep_redis_impl_when_initially_down() -> None:
    """启动时 Redis 不可用也应返回 Redis 实现（而非永久 NullCache），等待自动恢复。"""
    cache_service = await create_cache_service("redis://127.0.0.1:1/0")
    assert isinstance(cache_service, RedisCacheService)
    assert not cache_service.available
    assert await cache_service.get("any-key") is None


@pytest.mark.asyncio
async def test_redis_cache_should_bypass_gracefully_when_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RedisCacheService("redis://127.0.0.1:1/0")
    monkeypatch.setattr(service, "_redis", FlappingRedis())
    await service.set("key", "value", 60)
    assert await service.get("key") is None
    assert not service.available


@pytest.mark.asyncio
async def test_redis_cache_should_recover_automatically_after_redis_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis 恢复后无需重启即可自动接回缓存。"""
    monkeypatch.setattr("app.services.cache_service.RECONNECT_COOLDOWN_SECONDS", 0.0)
    service = RedisCacheService("redis://127.0.0.1:1/0")
    fake_redis = FlappingRedis()
    monkeypatch.setattr(service, "_redis", fake_redis)

    assert await service.get("key") is None
    assert not service.available

    fake_redis.healthy = True
    await service.set("key", "value", 60)
    assert service.available
    assert await service.get("key") == "value"


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
