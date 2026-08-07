"""滑动窗口限流器：内存（单实例）与 Redis（多实例共享计数）两种实现。

选型策略与缓存一致：Redis 可用则用 Redis 限流（多实例部署计数共享），
不可用时回退进程内存实现；Redis 判定失败时放行（fail-open），不阻断业务。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.services.cache_service import CacheService, RedisCacheService

logger = logging.getLogger(__name__)

DEFAULT_SWEEP_THRESHOLD = 10_000


class RateLimiter(Protocol):
    """限流器接口：判定指定 key（如客户端 IP）的当前请求是否放行。"""

    async def allow(self, key: str) -> bool:
        """放行返回 True，触发限流返回 False。"""
        ...  # pragma: no cover - 接口定义


class SlidingWindowRateLimiter:
    """进程内存滑动窗口限流器（单实例）。

    被访问的 key 若时间戳全部滑出窗口则立即删除；当 key 总量超过
    sweep_threshold 时再做一次全量清扫，保证长期运行内存占用有界。
    进程内存实现，多实例部署时不共享计数，此时应使用 Redis 实现。
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sweep_threshold: int = DEFAULT_SWEEP_THRESHOLD,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests 必须为正整数")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._sweep_threshold = sweep_threshold
        self._history: dict[str, deque[float]] = {}

    async def allow(self, key: str) -> bool:
        """判定当前请求是否放行；同时清理窗口外时间戳与已空闲的 key。"""
        now = self._clock()
        if len(self._history) > self._sweep_threshold:
            self._sweep(now)
        history = self._history.get(key)
        if history is not None:
            self._trim(history, now)
            if not history:
                # 该 key 在窗口内已无请求，删除以释放内存
                del self._history[key]
                history = None
        if history is not None and len(history) >= self._max_requests:
            return False
        if history is None:
            history = deque()
            self._history[key] = history
        history.append(now)
        return True

    def _trim(self, history: deque[float], now: float) -> None:
        """移除窗口外的历史时间戳。"""
        while history and now - history[0] > self._window_seconds:
            history.popleft()

    def _sweep(self, now: float) -> None:
        """全量清理已完全过期的 key（摊销触发，避免长期运行无界增长）。"""
        idle_keys = []
        for key, history in self._history.items():
            self._trim(history, now)
            if not history:
                idle_keys.append(key)
        for key in idle_keys:
            del self._history[key]


# 原子化滑动窗口判定：清窗口 -> 计数 -> 超限返回 0 -> 记录 -> 兜底过期
REDIS_ALLOW_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, tonumber(ARGV[1]) - tonumber(ARGV[2]))
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
  return 0
end
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), ARGV[4])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""


class RedisSlidingWindowRateLimiter:
    """Redis 滑动窗口限流器（多实例共享计数，语义与内存实现一致）。"""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        *,
        key_prefix: str,
        max_requests: int,
        window_seconds: float = 60.0,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests 必须为正整数")
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def allow(self, key: str) -> bool:
        """按 ZSET 滑动窗口判定；Redis 异常时放行（fail-open），不阻断业务。"""
        now_ms = int(time.time() * 1000)
        window_ms = int(self._window_seconds * 1000)
        try:
            result = await self._redis.eval(
                REDIS_ALLOW_LUA,
                1,
                f"{self._key_prefix}{key}",
                now_ms,
                window_ms,
                self._max_requests,
                uuid4().hex,
            )
        except RedisError as exc:
            logger.warning("Redis 限流判定失败，放行本次请求: %s", exc)
            return True
        return bool(result)


def create_rate_limiter(
    cache_service: CacheService,
    *,
    key_prefix: str,
    max_requests: int,
    window_seconds: float = 60.0,
) -> RateLimiter:
    """按缓存可用性选择限流实现：Redis 可用 -> 共享限流，否则 -> 进程内存限流。"""
    if isinstance(cache_service, RedisCacheService) and cache_service.available:
        logger.info("限流器[%s]使用 Redis 滑动窗口（多实例共享计数）", key_prefix)
        return RedisSlidingWindowRateLimiter(
            cache_service.client,
            key_prefix=key_prefix,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
    logger.info("限流器[%s]使用进程内存滑动窗口（单实例）", key_prefix)
    return SlidingWindowRateLimiter(max_requests, window_seconds)
