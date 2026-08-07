"""天气缓存：key 按 adcode，4h 新鲜度 + 24h 宽限，single-flight，stale 标记。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter

from app.models.schemas import WeatherInfo
from app.services.cache_service import CacheService
from app.services.errors import WeatherUnavailableError

logger = logging.getLogger(__name__)

WEATHER_FRESH_TTL = timedelta(hours=4)
WEATHER_GRACE_EXTRA = timedelta(hours=24)
WEATHER_KEY_PREFIX = "tripmate:weather:"
WEATHER_TTL_SECONDS = int(WEATHER_FRESH_TTL.total_seconds() + WEATHER_GRACE_EXTRA.total_seconds())

_weather_adapter = TypeAdapter(list[WeatherInfo])


class WeatherCacheEntry:
    """缓存条目：数据 + 抓取时间。"""

    def __init__(self, weather: list[WeatherInfo], fetched_at: datetime) -> None:
        self.weather = weather
        self.fetched_at = fetched_at


class WeatherCache:
    """天气缓存，负责新鲜度判定、single-flight 与 stale 降级。"""

    def __init__(
        self,
        cache_service: CacheService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cache = cache_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def build_key(adcode: str) -> str:
        return f"{WEATHER_KEY_PREFIX}{adcode}"

    async def get_or_refresh(
        self,
        adcode: str,
        fetch_func: Callable[[], Awaitable[list[WeatherInfo]]],
    ) -> tuple[list[WeatherInfo], datetime, bool]:
        """读取天气；命中新鲜缓存直接返回，否则单飞刷新。

        Returns:
            (天气列表, 数据更新时间, 是否 stale)。

        Raises:
            WeatherUnavailableError: 无任何缓存且刷新失败时。
        """
        key = self.build_key(adcode)
        now = self._clock()
        cached_entry = await self._read_entry(key)
        if cached_entry is not None:
            if now - cached_entry.fetched_at <= WEATHER_FRESH_TTL:
                return cached_entry.weather, cached_entry.fetched_at, False
            if now - cached_entry.fetched_at <= WEATHER_FRESH_TTL + WEATHER_GRACE_EXTRA:
                logger.info("天气数据超过 4h 新鲜期，返回 stale 数据(宽限期内): adcode=%s", adcode)
                return cached_entry.weather, cached_entry.fetched_at, True

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # 等待期间可能已被其他协程刷新
            cached_entry = await self._read_entry(key)
            if cached_entry is not None:
                if now - cached_entry.fetched_at <= WEATHER_FRESH_TTL:
                    return cached_entry.weather, cached_entry.fetched_at, False
                if now - cached_entry.fetched_at <= WEATHER_FRESH_TTL + WEATHER_GRACE_EXTRA:
                    return cached_entry.weather, cached_entry.fetched_at, True
            try:
                weather = await fetch_func()
            except Exception as exc:
                if cached_entry is not None:
                    logger.warning("天气刷新失败，返回旧数据并标记 stale: %s", exc)
                    return cached_entry.weather, cached_entry.fetched_at, True
                raise WeatherUnavailableError(f"天气服务暂不可用: {exc}") from exc
            fetched_at = self._clock()
            await self._write_entry(key, weather, fetched_at)
            return weather, fetched_at, False

    async def _read_entry(self, key: str) -> WeatherCacheEntry | None:
        raw = await self._cache.get(key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            weather = _weather_adapter.validate_python(payload["weather"])
            return WeatherCacheEntry(weather, fetched_at)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("天气缓存解析失败，视为未命中: %s", exc)
            return None

    async def _write_entry(
        self,
        key: str,
        weather: list[WeatherInfo],
        fetched_at: datetime,
    ) -> None:
        payload = json.dumps(
            {
                "fetched_at": fetched_at.isoformat(),
                "weather": [item.model_dump() for item in weather],
            },
            ensure_ascii=False,
        )
        await self._cache.set(key, payload, WEATHER_TTL_SECONDS)
