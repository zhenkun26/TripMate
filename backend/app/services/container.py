"""服务容器：集中装配各层依赖，便于测试替换。"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.llm_client import LLMClient
from app.agents.planner_agent import PlannerAgent
from app.services.amap_client import AmapClient
from app.services.cache_service import CacheService
from app.services.collection_service import CollectionService
from app.services.poi_cache import PoiCache
from app.services.static_map_service import StaticMapService
from app.services.weather_cache import WeatherCache


@dataclass
class Services:
    """后端全部可替换依赖的聚合容器。"""

    cache_service: CacheService
    amap_client: AmapClient
    weather_cache: WeatherCache
    poi_cache: PoiCache
    collection_service: CollectionService
    static_map_service: StaticMapService
    llm_client: LLMClient
    planner_agent: PlannerAgent
