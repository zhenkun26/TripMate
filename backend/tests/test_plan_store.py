"""行程分享存储单元测试：存取回环 / 缓存不可用降级 / 损坏数据。"""

from __future__ import annotations

import pytest

from app.services.plan_store import PLAN_SHARE_KEY_PREFIX, PlanStore
from tests.conftest import FakeCache, make_trip_plan


@pytest.mark.asyncio
async def test_should_roundtrip_trip_plan() -> None:
    store = PlanStore(FakeCache(), ttl_seconds=3600)
    token = await store.save(make_trip_plan())
    assert token is not None
    restored = await store.get(token)
    assert restored is not None
    assert restored.city == "北京"
    assert len(restored.days) == 3


@pytest.mark.asyncio
async def test_should_degrade_when_cache_unavailable() -> None:
    cache = FakeCache()
    cache.available = False
    store = PlanStore(cache, ttl_seconds=3600)
    assert await store.save(make_trip_plan()) is None
    assert await store.get("any-token") is None


@pytest.mark.asyncio
async def test_should_return_none_for_corrupted_payload() -> None:
    cache = FakeCache()
    store = PlanStore(cache, ttl_seconds=3600)
    await cache.set(f"{PLAN_SHARE_KEY_PREFIX}bad", "not-json", 60)
    assert await store.get("bad") is None
