"""缓存抽象：Redis 实现（断线按冷却时间自动重连）+ 空实现（显式绕过）。"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import redis.asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

RECONNECT_COOLDOWN_SECONDS = 5.0


class CacheService(ABC):
    """键值缓存抽象接口。"""

    @abstractmethod
    async def ping(self) -> bool:
        """探测缓存连通性（实时）。"""

    @property
    @abstractmethod
    def available(self) -> bool:
        """缓存当前是否可用。"""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """读取字符串值，未命中返回 None。"""

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """写入字符串值并设置 TTL。"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除指定 key。"""


class NullCacheService(CacheService):
    """空实现：Redis 不可用时直接绕过，保证缓存仅是优化层。"""

    async def ping(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        return False

    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None


class RedisCacheService(CacheService):
    """基于 redis.asyncio 的实现。

    任何 Redis 异常都降级为未命中而不向上抛；断线后按冷却时间惰性重连，
    Redis 恢复后无需重启即可自动接回缓存。
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        self._healthy = False
        self._last_reconnect_attempt = 0.0

    @property
    def available(self) -> bool:
        return self._healthy

    @property
    def client(self) -> aioredis.Redis:
        """底层 Redis 客户端，供限流器等组件复用同一连接池。"""
        return self._redis

    async def ping(self) -> bool:
        """探测 Redis 连通性，成功则标记健康。"""
        try:
            await self._redis.ping()
            self._healthy = True
            return True
        except RedisError as exc:
            self._healthy = False
            logger.warning("Redis 不可用，缓存将绕过直调: %s", exc)
            return False

    async def _ensure_connection(self) -> bool:
        """健康则直接通过；不健康时按冷却时间尝试重连，避免每次请求都阻塞在重连上。"""
        if self._healthy:
            return True
        now = time.monotonic()
        if now - self._last_reconnect_attempt < RECONNECT_COOLDOWN_SECONDS:
            return False
        self._last_reconnect_attempt = now
        return await self.ping()

    async def get(self, key: str) -> str | None:
        if not await self._ensure_connection():
            return None
        try:
            raw_value = await self._redis.get(key)
        except RedisError as exc:
            self._healthy = False
            logger.warning("Redis get 失败，降级直调: %s", exc)
            return None
        if raw_value is None:
            return None
        if isinstance(raw_value, bytes):
            return raw_value.decode("utf-8")
        return raw_value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if not await self._ensure_connection():
            return None
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
        except RedisError as exc:
            self._healthy = False
            logger.warning("Redis set 失败，降级直调: %s", exc)

    async def delete(self, key: str) -> None:
        if not await self._ensure_connection():
            return None
        try:
            await self._redis.delete(key)
        except RedisError as exc:
            self._healthy = False
            logger.warning("Redis delete 失败: %s", exc)


async def create_cache_service(redis_url: str) -> CacheService:
    """创建缓存服务：始终返回 Redis 实现（断线自动重连，失败时逐请求降级直调）。"""
    redis_cache = RedisCacheService(redis_url)
    await redis_cache.ping()
    return redis_cache
