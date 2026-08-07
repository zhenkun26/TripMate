"""候选集构建：高德原始 POI -> 结构化候选（评分过滤、截断、坐标校验、poi_id 保留）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.models.schemas import Location

logger = logging.getLogger(__name__)

ATTRACTION_TOP_N = 15
ATTRACTION_MIN_RATING = 4.0
HOTEL_TOP_N = 8


@dataclass(frozen=True)
class AttractionCandidate:
    """可被 PlannerAgent 引用的真实景点候选。"""

    poi_id: str
    name: str
    address: str
    location: Location
    category: str
    rating: float | None
    adcode: str


@dataclass(frozen=True)
class HotelCandidate:
    """可被 PlannerAgent 引用的真实酒店候选。"""

    poi_id: str
    name: str
    address: str
    location: Location | None
    type: str
    rating: str
    price_range: str


def _parse_location(location_value: object) -> Location | None:
    """解析高德 "lng,lat" 坐标字符串，非法坐标返回 None。"""
    if not isinstance(location_value, str):
        return None
    parts = location_value.split(",")
    if len(parts) != 2:
        return None
    try:
        longitude = float(parts[0])
        latitude = float(parts[1])
    except ValueError:
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    return Location(longitude=longitude, latitude=latitude)


def _parse_rating(rating_value: object) -> float | None:
    """解析评分字符串；空值返回 None。"""
    if rating_value is None or rating_value == "":
        return None
    try:
        rating = float(str(rating_value))
    except ValueError:
        return None
    return rating if 0 <= rating <= 5 else None


def _to_text(value: object) -> str:
    return str(value) if value is not None else ""


def build_attraction_candidates(raw_pois: list[dict[str, Any]]) -> list[AttractionCandidate]:
    """构建景点候选：坐标校验 + 评分 ≥4.0 过滤（无评分保留）+ 按评分降序取 top-15。"""
    candidates: list[AttractionCandidate] = []
    for raw_poi in raw_pois:
        location = _parse_location(raw_poi.get("location"))
        if location is None:
            logger.debug("丢弃无有效坐标的 POI: %s", raw_poi.get("name"))
            continue
        poi_id = _to_text(raw_poi.get("id"))
        name = _to_text(raw_poi.get("name"))
        if not poi_id or not name:
            continue
        rating = _parse_rating(raw_poi.get("rating"))
        if rating is not None and rating < ATTRACTION_MIN_RATING:
            continue
        candidates.append(
            AttractionCandidate(
                poi_id=poi_id,
                name=name,
                address=_to_text(raw_poi.get("address")),
                location=location,
                category=_to_text(raw_poi.get("type")),
                rating=rating,
                adcode=_to_text(raw_poi.get("adcode")),
            )
        )
    candidates.sort(key=lambda item: (item.rating is None, -(item.rating or 0.0)))
    return candidates[:ATTRACTION_TOP_N]


def build_hotel_candidates(raw_pois: list[dict[str, Any]]) -> list[HotelCandidate]:
    """构建酒店候选：坐标/名称校验，取前 top-8。"""
    candidates: list[HotelCandidate] = []
    for raw_poi in raw_pois:
        poi_id = _to_text(raw_poi.get("id"))
        name = _to_text(raw_poi.get("name"))
        if not poi_id or not name:
            continue
        candidates.append(
            HotelCandidate(
                poi_id=poi_id,
                name=name,
                address=_to_text(raw_poi.get("address")),
                location=_parse_location(raw_poi.get("location")),
                type=_to_text(raw_poi.get("type")),
                rating=_to_text(raw_poi.get("rating")),
                price_range=_extract_hotel_price(raw_poi),
            )
        )
    return candidates[:HOTEL_TOP_N]


def _extract_hotel_price(raw_poi: dict[str, Any]) -> str:
    """从 biz_ext.cost 提取酒店价格信息，缺失时返回空串。"""
    biz_ext = raw_poi.get("biz_ext")
    if isinstance(biz_ext, dict):
        cost = biz_ext.get("cost")
        if isinstance(cost, str) and cost:
            return f"约{cost}元/晚"
    return ""
