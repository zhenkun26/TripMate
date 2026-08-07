"""静态图代理单元测试：参数构建、token、缓存、限流、防篡改。"""

from __future__ import annotations

import pytest

from app.services.errors import StaticMapNotFoundError, StaticMapRateLimitError
from app.services.static_map_service import (
    DAY_COLORS,
    StaticMapService,
    build_static_map_params,
)
from tests.conftest import FakeAmapClient, FakeCache, make_trip_plan


def build_service(
    cache: FakeCache | None = None,
    rate_limit_per_minute: int = 60,
) -> StaticMapService:
    """装配静态图服务。"""
    return StaticMapService(
        cache or FakeCache(),
        FakeAmapClient(),
        size="750x400",
        token_ttl_seconds=86400,
        rate_limit_per_minute=rate_limit_per_minute,
    )


def test_should_build_markers_and_cross_day_paths() -> None:
    trip_plan = make_trip_plan()
    params = build_static_map_params(trip_plan, "750x400")
    assert params is not None
    assert params["size"] == "750x400"
    assert params["markers"].count("mid,") == 6
    assert params["paths"].count(";") == 2
    assert DAY_COLORS[0] in params["markers"]


def test_should_return_none_when_no_attractions() -> None:
    trip_plan = make_trip_plan()
    trip_plan.days = []
    assert build_static_map_params(trip_plan, "750x400") is None


@pytest.mark.asyncio
async def test_create_token_should_store_params_and_return_token() -> None:
    cache = FakeCache()
    service = build_service(cache)
    token = await service.create_map_token(make_trip_plan())
    assert token is not None
    stored = await cache.get(f"tripmate:staticmap:{token}")
    assert stored is not None and "markers" in stored


@pytest.mark.asyncio
async def test_create_token_should_return_none_when_cache_unavailable() -> None:
    cache = FakeCache()
    cache.available = False
    service = build_service(cache)
    assert await service.create_map_token(make_trip_plan()) is None


@pytest.mark.asyncio
async def test_render_should_cache_image_and_avoid_repeated_amap_calls() -> None:
    cache = FakeCache()
    amap = FakeAmapClient()
    service = StaticMapService(
        cache,
        amap,
        size="750x400",
        token_ttl_seconds=86400,
        rate_limit_per_minute=60,
    )
    token = await service.create_map_token(make_trip_plan())
    assert token is not None

    first_image = await service.render_map_image(token, "127.0.0.1")
    second_image = await service.render_map_image(token, "127.0.0.1")

    assert first_image == second_image == b"\x89PNG\r\n\x1a\nfake-static-map"
    assert amap.static_map_calls == 1


@pytest.mark.asyncio
async def test_render_should_raise_not_found_for_unknown_token() -> None:
    service = build_service()
    with pytest.raises(StaticMapNotFoundError):
        await service.render_map_image("forged-token", "127.0.0.1")


@pytest.mark.asyncio
async def test_render_should_raise_not_found_for_tampered_params() -> None:
    cache = FakeCache()
    service = build_service(cache)
    await cache.set("tripmate:staticmap:bad", "{not-json", 3600)
    with pytest.raises(StaticMapNotFoundError):
        await service.render_map_image("bad", "127.0.0.1")


@pytest.mark.asyncio
async def test_rate_limiter_should_block_excess_requests() -> None:
    service = build_service(rate_limit_per_minute=1)
    token = await service.create_map_token(make_trip_plan())
    assert token is not None
    await service.render_map_image(token, "10.0.0.1")
    with pytest.raises(StaticMapRateLimitError):
        await service.render_map_image(token, "10.0.0.1")
