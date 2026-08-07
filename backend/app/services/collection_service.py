"""三路并行数据采集编排：景点 POI / 酒店 POI / 天气，全部经缓存层。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.schemas import WeatherInfo
from app.services.amap_client import AmapClient
from app.services.cache_service import CacheService
from app.services.candidate_service import (
    AttractionCandidate,
    HotelCandidate,
    build_attraction_candidates,
    build_hotel_candidates,
)
from app.services.errors import AmapError, WeatherUnavailableError
from app.services.poi_cache import (
    PoiCache,
    map_accommodation_to_keywords,
    map_preferences_to_keywords,
)
from app.services.weather_cache import WeatherCache

logger = logging.getLogger(__name__)

CITY_ADCODE_CACHE_PREFIX = "tripmate:cityadcode:"
CITY_ADCODE_TTL_SECONDS = 7 * 24 * 60 * 60
WEATHER_UNAVAILABLE_NOTICE = "天气服务暂不可用，未能获取天气数据"
HOTEL_UNAVAILABLE_NOTICE = "酒店数据获取失败，建议按预算档位自行预订"


@dataclass
class CollectionResult:
    """一次规划请求对应的真实候选数据集合。"""

    adcode: str
    attractions: list[AttractionCandidate]
    hotels: list[HotelCandidate]
    weather: list[WeatherInfo]
    weather_updated_at: datetime | None
    weather_stale: bool
    notices: list[str]


class CollectionService:
    """负责城市编码解析与三路并行采集，缓存由 PoiCache/WeatherCache 承担。"""

    def __init__(
        self,
        amap_client: AmapClient,
        cache_service: CacheService,
        poi_cache: PoiCache,
        weather_cache: WeatherCache,
    ) -> None:
        self._amap = amap_client
        self._cache = cache_service
        self._poi_cache = poi_cache
        self._weather_cache = weather_cache

    async def collect(
        self,
        city: str,
        preferences: str,
        accommodation: str,
    ) -> CollectionResult:
        """并行采集景点/酒店/天气；景点失败视为致命，酒店/天气失败降级并给出提示。"""
        adcode = await self._resolve_adcode(city)
        attraction_keywords = map_preferences_to_keywords(preferences)
        hotel_keywords = map_accommodation_to_keywords(accommodation)

        attraction_task = self._poi_cache.get_or_fetch(
            adcode,
            "attraction",
            attraction_keywords,
            lambda: self._amap.search_pois(city, attraction_keywords),
        )
        hotel_task = self._poi_cache.get_or_fetch(
            adcode,
            "hotel",
            hotel_keywords,
            lambda: self._amap.search_pois(city, hotel_keywords),
        )
        weather_task = self._weather_cache.get_or_refresh(
            adcode,
            lambda: self._fetch_weather_entries(adcode),
        )

        results = await asyncio.gather(
            attraction_task,
            hotel_task,
            weather_task,
            return_exceptions=True,
        )

        attractions_result = results[0]
        if isinstance(attractions_result, BaseException):
            raise AmapError(f"景点数据获取失败: {attractions_result}", status_code=502)
        attractions_raw_pois, _ = attractions_result

        notices: list[str] = []
        hotels: list[HotelCandidate] = []
        hotels_result = results[1]
        if isinstance(hotels_result, BaseException):
            logger.warning("酒店数据获取失败，降级为无酒店: %s", hotels_result)
            notices.append(HOTEL_UNAVAILABLE_NOTICE)
        else:
            hotels_raw_pois, _ = hotels_result
            hotels = build_hotel_candidates(hotels_raw_pois)

        weather: list[WeatherInfo] = []
        weather_updated_at: datetime | None = None
        weather_stale = False
        weather_result = results[2]
        if isinstance(weather_result, BaseException):
            if isinstance(weather_result, WeatherUnavailableError):
                logger.warning("天气不可用，降级为无天气: %s", weather_result)
                notices.append(WEATHER_UNAVAILABLE_NOTICE)
            else:
                raise AmapError(f"天气数据获取失败: {weather_result}", status_code=502)
        else:
            weather, weather_updated_at, weather_stale = weather_result
            if weather_stale:
                notices.append("天气数据存在延迟，仅供参考")

        attractions = build_attraction_candidates(attractions_raw_pois)
        return CollectionResult(
            adcode=adcode,
            attractions=attractions,
            hotels=hotels,
            weather=weather,
            weather_updated_at=weather_updated_at,
            weather_stale=weather_stale,
            notices=notices,
        )

    async def _resolve_adcode(self, city: str) -> str:
        """解析城市 adcode（缓存 7 天）；用于天气接口与 POI 缓存 key。"""
        cache_key = f"{CITY_ADCODE_CACHE_PREFIX}{city.strip()}"
        cached = await self._cache.get(cache_key)
        if cached:
            return cached
        raw_pois = await self._amap.search_pois(city, [city])
        adcode = self._extract_adcode(raw_pois)
        if not adcode:
            raise AmapError(f"无法确定城市 {city} 的行政编码", status_code=502)
        await self._cache.set(cache_key, adcode, CITY_ADCODE_TTL_SECONDS)
        return adcode

    @staticmethod
    def _extract_adcode(raw_pois: list[dict[str, Any]]) -> str:
        """从 POI 检索结果中提取首个非空 adcode，找不到时返回空串。"""
        for raw_poi in raw_pois:
            adcode = raw_poi.get("adcode")
            if isinstance(adcode, str) and adcode:
                return adcode
        return ""

    async def _fetch_weather_entries(self, adcode: str) -> list[WeatherInfo]:
        """调用高德天气接口并解析为 WeatherInfo 列表（今日+未来3天）。"""
        payload = await self._amap.get_weather(adcode)
        forecasts = payload.get("forecasts")
        if not isinstance(forecasts, list) or not forecasts:
            raise WeatherUnavailableError("高德天气响应缺少预报数据")
        casts = forecasts[0].get("casts")
        if not isinstance(casts, list):
            raise WeatherUnavailableError("高德天气响应缺少预报日期数据")
        weather_entries: list[WeatherInfo] = []
        for cast in casts:
            if not isinstance(cast, dict):
                continue
            date_value = cast.get("date")
            if not isinstance(date_value, str) or not date_value:
                continue
            weather_entries.append(
                WeatherInfo(
                    date=date_value,
                    day_weather=_text(cast.get("dayweather")),
                    night_weather=_text(cast.get("nightweather")),
                    day_temp=cast.get("daytemp") or 0,
                    night_temp=cast.get("nighttemp") or 0,
                    wind_direction=_text(cast.get("daywind")),
                    wind_power=_text(cast.get("daypower")),
                )
            )
        return weather_entries
def _text(value: object) -> str:
    return str(value) if value is not None else ""
