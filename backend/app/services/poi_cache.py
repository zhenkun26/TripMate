"""POI 缓存：偏好/住宿类型映射为规范查询，48h 新鲜度 + 7d 宽限，空结果短 TTL。"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from app.services.cache_service import CacheService
from app.services.errors import AmapError

logger = logging.getLogger(__name__)

POI_FRESH_TTL = timedelta(hours=48)
POI_GRACE_EXTRA = timedelta(days=7)
POI_EMPTY_TTL_SECONDS = 30 * 60
POI_KEY_PREFIX = "tripmate:poi:v1:"
POI_TTL_SECONDS = int(POI_FRESH_TTL.total_seconds() + POI_GRACE_EXTRA.total_seconds())


class PoiCacheEntry(TypedDict):
    """缓存的 POI 条目结构。"""

    fetched_at: datetime
    pois: list[dict[str, object]]


def _query_fingerprint(query_keywords: list[str]) -> str:
    """按规范查询关键词生成缓存指纹，保证相同偏好可命中同一缓存。"""
    normalized = "|".join(query_keywords).strip().lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def map_preferences_to_keywords(preferences: str) -> list[str]:
    """把用户偏好文本映射为高德可用的规范查询关键词。"""
    text = preferences.strip()
    preference_rules: list[tuple[list[str], list[str]]] = [
        (["历史", "文化", "古迹", "博物馆", "人文"], ["博物馆", "历史遗迹", "文化"]),
        (["自然", "山水", "风景", "公园", "户外"], ["风景名胜", "公园", "自然"]),
        (["亲子", "乐园", "儿童", "动物园"], ["主题乐园", "动物园", "公园"]),
        (["都市", "购物", "休闲", "美食"], ["地标", "购物中心", "公园"]),
        (["海边", "海岛", "海滩"], ["海滨", "海岛", "公园"]),
    ]
    for keywords, canonical in preference_rules:
        if any(keyword in text for keyword in keywords):
            return canonical
    return ["景点"]


def map_accommodation_to_keywords(accommodation: str) -> list[str]:
    """把住宿类型映射为酒店查询关键词。"""
    text = accommodation.strip()
    accommodation_rules: list[tuple[list[str], str]] = [
        (["经济", "快捷", "青旅"], "经济型酒店"),
        (["舒适", "商务"], "舒适型酒店"),
        (["豪华", "五星", "高星"], "豪华酒店"),
        (["民宿"], "民宿"),
    ]
    for keywords, canonical in accommodation_rules:
        if any(keyword in text for keyword in keywords):
            return [canonical]
    return ["酒店"]


class PoiCache:
    """POI 缓存，返回 (原始 POI 列表, 是否 stale)。"""

    def __init__(
        self,
        cache_service: CacheService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cache = cache_service
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def build_key(adcode: str, category: str, query_keywords: list[str]) -> str:
        fingerprint = _query_fingerprint(query_keywords)
        return f"{POI_KEY_PREFIX}{adcode}:{category}:{fingerprint}"

    async def get_or_fetch(
        self,
        adcode: str,
        category: str,
        query_keywords: list[str],
        fetch_func: Callable[[], Awaitable[list[dict[str, object]]]],
    ) -> tuple[list[dict[str, object]], bool]:
        """读取 POI 缓存；命中返回，未命中/过期则抓取并回填。

        Raises:
            AmapError: 无缓存且抓取失败时。
        """
        key = self.build_key(adcode, category, query_keywords)
        now = self._clock()
        cached_entry = await self._read_entry(key)
        if cached_entry is not None:
            if now - cached_entry["fetched_at"] <= POI_FRESH_TTL:
                return cached_entry["pois"], False
            if now - cached_entry["fetched_at"] <= POI_FRESH_TTL + POI_GRACE_EXTRA:
                logger.info("POI 数据超过 48h 新鲜期，返回 stale 数据(宽限期内): %s", key)
                return cached_entry["pois"], True

        try:
            pois = await fetch_func()
        except Exception as exc:
            if cached_entry is not None:
                logger.warning("POI 刷新失败，返回旧数据并标记 stale: %s", exc)
                return cached_entry["pois"], True
            raise AmapError(f"POI 数据获取失败: {exc}") from exc

        await self._write_entry(key, pois)
        return pois, False

    async def _read_entry(self, key: str) -> PoiCacheEntry | None:
        raw = await self._cache.get(key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            fetched_at = datetime.fromisoformat(str(payload["fetched_at"]))
            raw_pois = payload["pois"]
            if not isinstance(raw_pois, list):
                raise ValueError("pois 不是列表")
            pois: list[dict[str, object]] = [item for item in raw_pois if isinstance(item, dict)]
            return PoiCacheEntry(fetched_at=fetched_at, pois=pois)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("POI 缓存解析失败，视为未命中: %s", exc)
            return None

    async def _write_entry(self, key: str, pois: list[dict[str, object]]) -> None:
        payload = json.dumps(
            {"fetched_at": self._clock().isoformat(), "pois": pois},
            ensure_ascii=False,
        )
        ttl = POI_EMPTY_TTL_SECONDS if not pois else POI_TTL_SECONDS
        await self._cache.set(key, payload, ttl)
