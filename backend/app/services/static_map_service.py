"""静态图代理：不透明 token 签发、参数构建、Redis 图片缓存与单 IP 限流。"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import time
from collections import defaultdict, deque

from app.models.schemas import TripPlan
from app.services.amap_client import AmapClient
from app.services.cache_service import CacheService
from app.services.errors import StaticMapNotFoundError, StaticMapRateLimitError

logger = logging.getLogger(__name__)

STATIC_MAP_TOKEN_PREFIX = "tripmate:staticmap:"
STATIC_MAP_IMG_PREFIX = "tripmate:staticmap:img:"
DAY_COLORS = [
    "0x1E90FF",
    "0xFF8C00",
    "0x32CD32",
    "0xDA70D6",
    "0x20B2AA",
    "0xFF69B4",
    "0x8A2BE2",
    "0xCD853F",
    "0x5F9EA0",
    "0xDC143C",
]
# 跨天连接线：浅色细线（高德静态图不支持虚线时的降级方案）
CROSS_DAY_PATH_COLOR = "0xB0BEC5"
CROSS_DAY_PATH_WEIGHT = "2"
DEFAULT_ZOOM = 12
MIN_ZOOM = 10
MAX_ZOOM = 15


class SlidingWindowRateLimiter:
    """内存滑动窗口限流器（按 key，如客户端 IP）。"""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """判定当前请求是否放行；同时清理窗口外时间戳。"""
        now = time.monotonic()
        history = self._history[key]
        while history and now - history[0] > self._window_seconds:
            history.popleft()
        if len(history) >= self._max_requests:
            return False
        history.append(now)
        return True


def build_static_map_params(trip_plan: TripPlan, size: str) -> dict[str, str] | None:
    """根据行程构建高德静态图参数；无景点坐标时返回 None。"""
    markers: list[str] = []
    ordered_points: list[tuple[float, float]] = []
    global_index = 1
    for day_index, day in enumerate(trip_plan.days):
        color = DAY_COLORS[day_index % len(DAY_COLORS)]
        for attraction in day.attractions:
            longitude = attraction.location.longitude
            latitude = attraction.location.latitude
            markers.append(f"mid,{color},{global_index}:{longitude},{latitude}")
            ordered_points.append((longitude, latitude))
            global_index += 1
    if not markers:
        return None

    paths: list[str] = []
    for day_index in range(len(trip_plan.days) - 1):
        current_day = trip_plan.days[day_index]
        next_day = trip_plan.days[day_index + 1]
        if not current_day.attractions or not next_day.attractions:
            continue
        end_point = current_day.attractions[-1].location
        start_point = next_day.attractions[0].location
        paths.append(
            f"{CROSS_DAY_PATH_WEIGHT},{CROSS_DAY_PATH_COLOR}:"
            f"{end_point.longitude},{end_point.latitude};"
            f"{start_point.longitude},{start_point.latitude}"
        )

    center_longitude = sum(point[0] for point in ordered_points) / len(ordered_points)
    center_latitude = sum(point[1] for point in ordered_points) / len(ordered_points)
    longitude_span = (
        max(point[0] for point in ordered_points) - min(point[0] for point in ordered_points)
    )
    latitude_span = (
        max(point[1] for point in ordered_points) - min(point[1] for point in ordered_points)
    )
    zoom = _compute_zoom(max(longitude_span, latitude_span))

    params: dict[str, str] = {
        "location": f"{center_longitude:.6f},{center_latitude:.6f}",
        "zoom": str(zoom),
        "size": size,
        "markers": "|".join(markers),
    }
    if paths:
        params["paths"] = "|".join(paths)
    return params


def _compute_zoom(max_span: float) -> int:
    """根据坐标跨度估算缩放级别，保证全部标记可见。"""
    if max_span <= 0.0:
        return DEFAULT_ZOOM
    zoom = int(DEFAULT_ZOOM - max(0.0, (max_span - 0.15) / 0.45))
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


class StaticMapService:
    """负责 token 生命周期：签发 -> 参数存储 -> 图片生成/缓存。"""

    def __init__(
        self,
        cache_service: CacheService,
        amap_client: AmapClient,
        *,
        size: str,
        token_ttl_seconds: int,
        rate_limit_per_minute: int,
    ) -> None:
        self._cache = cache_service
        self._amap = amap_client
        self._size = size
        self._token_ttl_seconds = token_ttl_seconds
        self._rate_limiter = SlidingWindowRateLimiter(rate_limit_per_minute)

    async def create_map_token(self, trip_plan: TripPlan) -> str | None:
        """生成并存储静态图参数 token；Redis 不可用或无坐标时返回 None。"""
        params = build_static_map_params(trip_plan, self._size)
        if params is None or not self._cache.available:
            return None
        token = secrets.token_urlsafe(24)
        await self._cache.set(
            f"{STATIC_MAP_TOKEN_PREFIX}{token}",
            json.dumps(params, ensure_ascii=False),
            self._token_ttl_seconds,
        )
        return token

    async def render_map_image(self, token: str, client_ip: str) -> bytes:
        """按 token 渲染静态图；命中缓存直接返回，否则调用高德并回填。"""
        if not self._rate_limiter.allow(client_ip):
            raise StaticMapRateLimitError()
        raw_params = await self._cache.get(f"{STATIC_MAP_TOKEN_PREFIX}{token}")
        if raw_params is None:
            raise StaticMapNotFoundError()
        try:
            params = json.loads(raw_params)
        except json.JSONDecodeError as exc:
            raise StaticMapNotFoundError() from exc

        cached_image = await self._cache.get(f"{STATIC_MAP_IMG_PREFIX}{token}")
        if cached_image is not None:
            return base64.b64decode(cached_image)

        image_bytes = await self._amap.fetch_static_map(params)
        await self._cache.set(
            f"{STATIC_MAP_IMG_PREFIX}{token}",
            base64.b64encode(image_bytes).decode("ascii"),
            self._token_ttl_seconds,
        )
        return image_bytes
