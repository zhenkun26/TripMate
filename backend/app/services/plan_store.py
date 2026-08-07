"""行程分享存储：TripPlan 序列化入缓存，凭不透明 token 取回（分享链接的后端支撑）。

复用与静态图相同的「不透明 token + 缓存 TTL」模式；缓存不可用时优雅降级
（save 返回 None，主流程不受影响），与 Redis 仅作优化层的哲学一致。
"""

from __future__ import annotations

import logging
import secrets

from pydantic import ValidationError

from app.models.schemas import TripPlan
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

PLAN_SHARE_KEY_PREFIX = "tripmate:plan:share:"


class PlanStore:
    """分享行程的存取：签发 token -> 序列化存储 -> 按 token 取回。"""

    def __init__(self, cache_service: CacheService, *, ttl_seconds: int) -> None:
        self._cache = cache_service
        self._ttl_seconds = ttl_seconds

    async def save(self, trip_plan: TripPlan) -> str | None:
        """存储行程并返回分享 token；缓存不可用时返回 None。"""
        if not self._cache.available:
            return None
        token = secrets.token_urlsafe(24)
        await self._cache.set(
            f"{PLAN_SHARE_KEY_PREFIX}{token}",
            trip_plan.model_dump_json(),
            self._ttl_seconds,
        )
        return token

    async def get(self, token: str) -> TripPlan | None:
        """按 token 取回行程；不存在、已过期或数据损坏时返回 None。"""
        raw = await self._cache.get(f"{PLAN_SHARE_KEY_PREFIX}{token}")
        if raw is None:
            return None
        try:
            return TripPlan.model_validate_json(raw)
        except ValidationError as exc:
            logger.warning("分享行程数据解析失败，视为不存在: %s", exc)
            return None
