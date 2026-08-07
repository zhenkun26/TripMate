"""限流器单元测试：内存实现放行/拦截/窗口滑动/清扫；Redis 实现语义/fail-open；工厂选型。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.cache_service import RedisCacheService
from app.services.rate_limit import (
    RedisSlidingWindowRateLimiter,
    SlidingWindowRateLimiter,
    create_rate_limiter,
)
from tests.conftest import FakeCache


class FakeMonotonic:
    """可手动推进的单调时钟。"""

    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


def test_should_reject_non_positive_max_requests() -> None:
    with pytest.raises(ValueError, match="正整数"):
        SlidingWindowRateLimiter(0)
    with pytest.raises(ValueError, match="正整数"):
        RedisSlidingWindowRateLimiter(
            FakeRedisEval(),  # type: ignore[arg-type]
            key_prefix="test:",
            max_requests=0,
        )


@pytest.mark.asyncio
async def test_should_allow_up_to_max_requests_then_block() -> None:
    limiter = SlidingWindowRateLimiter(3, clock=FakeMonotonic())
    assert [await limiter.allow("ip1") for _ in range(3)] == [True, True, True]
    assert not await limiter.allow("ip1")


@pytest.mark.asyncio
async def test_should_track_keys_independently() -> None:
    limiter = SlidingWindowRateLimiter(1, clock=FakeMonotonic())
    assert await limiter.allow("ip1")
    assert not await limiter.allow("ip1")
    assert await limiter.allow("ip2")


@pytest.mark.asyncio
async def test_should_allow_again_after_window_slides() -> None:
    clock = FakeMonotonic()
    limiter = SlidingWindowRateLimiter(1, window_seconds=60.0, clock=clock)
    assert await limiter.allow("ip1")
    assert not await limiter.allow("ip1")
    clock.advance(61.0)
    assert await limiter.allow("ip1")


@pytest.mark.asyncio
async def test_should_evict_accessed_key_once_fully_expired() -> None:
    clock = FakeMonotonic()
    limiter = SlidingWindowRateLimiter(2, window_seconds=60.0, clock=clock)
    await limiter.allow("ip1")
    clock.advance(120.0)
    assert await limiter.allow("ip1")  # 旧时间戳过期 -> 重新计数并放行
    assert len(limiter._history["ip1"]) == 1


@pytest.mark.asyncio
async def test_should_sweep_expired_keys_when_history_grows() -> None:
    clock = FakeMonotonic()
    limiter = SlidingWindowRateLimiter(5, window_seconds=60.0, clock=clock, sweep_threshold=2)
    await limiter.allow("ip1")
    clock.advance(120.0)
    await limiter.allow("ip2")
    await limiter.allow("ip3")
    await limiter.allow("ip4")  # 触发全量清扫：ip1 已过期应被移除
    assert "ip1" not in limiter._history
    assert "ip2" in limiter._history
    assert "ip4" in limiter._history


class FakeRedisEval:
    """用内存 ZSET 语义模拟 Redis eval 的假客户端（与 Lua 脚本逻辑一致）。"""

    def __init__(self) -> None:
        self._zsets: dict[str, dict[str, float]] = {}
        self.fail = False

    async def eval(self, script: str, numkeys: int, *args: object) -> int:
        if self.fail:
            raise RedisConnectionError("connection refused")
        key = str(args[0])
        now_ms = float(str(args[1]))
        window_ms = float(str(args[2]))
        max_requests = int(str(args[3]))
        member = str(args[4])
        zset = self._zsets.setdefault(key, {})
        expired = [m for m, score in zset.items() if score <= now_ms - window_ms]
        for m in expired:
            del zset[m]
        if len(zset) >= max_requests:
            return 0
        zset[member] = now_ms
        return 1


@pytest_asyncio.fixture
async def fake_redis_eval() -> FakeRedisEval:
    return FakeRedisEval()


@pytest.mark.asyncio
async def test_redis_limiter_should_match_memory_semantics(
    fake_redis_eval: FakeRedisEval,
) -> None:
    limiter = RedisSlidingWindowRateLimiter(
        fake_redis_eval,  # type: ignore[arg-type]
        key_prefix="test:",
        max_requests=2,
        window_seconds=60.0,
    )
    assert await limiter.allow("ip1")
    assert await limiter.allow("ip1")
    assert not await limiter.allow("ip1")
    assert await limiter.allow("ip2")


@pytest.mark.asyncio
async def test_redis_limiter_should_fail_open_on_redis_error(
    fake_redis_eval: FakeRedisEval,
) -> None:
    fake_redis_eval.fail = True
    limiter = RedisSlidingWindowRateLimiter(
        fake_redis_eval,  # type: ignore[arg-type]
        key_prefix="test:",
        max_requests=1,
    )
    assert await limiter.allow("ip1")


def test_factory_should_fallback_to_memory_when_cache_not_redis() -> None:
    limiter = create_rate_limiter(FakeCache(), key_prefix="test:", max_requests=10)
    assert isinstance(limiter, SlidingWindowRateLimiter)


def test_factory_should_fallback_to_memory_when_redis_unhealthy() -> None:
    redis_cache = RedisCacheService("redis://127.0.0.1:1/0")
    limiter = create_rate_limiter(redis_cache, key_prefix="test:", max_requests=10)
    assert isinstance(limiter, SlidingWindowRateLimiter)


def test_factory_should_use_redis_when_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_cache = RedisCacheService("redis://127.0.0.1:1/0")
    monkeypatch.setattr(redis_cache, "_healthy", True)
    limiter = create_rate_limiter(redis_cache, key_prefix="test:", max_requests=10)
    assert isinstance(limiter, RedisSlidingWindowRateLimiter)
