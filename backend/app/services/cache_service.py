"""缓存抽象：Redis 实现 + 不可用时自动绕过（NullCache）。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import redis.asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


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
    """基于 redis.asyncio 的实现；任何 Redis 异常都降级为未命中而不向上抛。"""

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        self._healthy = False

    @property
    def available(self) -> bool:
        return self._healthy

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

    async def get(self, key: str) -> str | None:
        if not self._healthy:
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
        if not self._healthy:
            return None
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
        except RedisError as exc:
            self._healthy = False
            logger.warning("Redis set 失败，降级直调: %s", exc)

    async def delete(self, key: str) -> None:
        if not self._healthy:
            return None
        try:
            await self._redis.delete(key)
        except RedisError as exc:
            self._healthy = False
            logger.warning("Redis delete 失败: %s", exc)


async def create_cache_service(redis_url: str) -> CacheService:
    """创建缓存服务：连通则返回 Redis 实现，否则返回 NullCache 绕过。"""
    redis_cache = RedisCacheService(redis_url)
    if await redis_cache.ping():
        return redis_cache
    return NullCacheService()
