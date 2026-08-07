"""PlannerAgent：一次 LLM 调用双规划 + Pydantic 校验 + 修复重试(≤2) + 确定性后处理。"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from pydantic import ValidationError

from app.agents.llm_client import LLMClient
from app.agents.prompts.planner_prompt_v1 import (
    PLANNER_REPAIR_PROMPT_V1,
    PLANNER_SYSTEM_PROMPT_V1,
    build_user_package,
)
from app.models.schemas import (
    Attraction,
    DayPlan,
    Hotel,
    TripPlan,
    TripPlanDraft,
    TripPlanRequest,
    WeatherInfo,
)
from app.services.budget_service import recalculate_budget
from app.services.candidate_service import AttractionCandidate, HotelCandidate
from app.services.collection_service import CollectionResult
from app.services.errors import (
    LLMOutputError,
    LLMUnavailableError,
    PlanValidationError,
    StructuredOutputNotSupported,
)
from app.services.static_map_service import StaticMapService

logger = logging.getLogger(__name__)

NO_HOTEL_NOTICE = "暂未找到合适的酒店，建议按预算档位自行预订"


class PlannerAgent:
    """行程规划智能体：生成 -> 校验/修复(≤2) -> 真实数据注入 -> 预算重算。"""

    def __init__(
        self,
        llm_client: LLMClient,
        static_map_service: StaticMapService,
        max_repair_attempts: int = 2,
    ) -> None:
        self._llm = llm_client
        self._static_map = static_map_service
        self._max_repair_attempts = max_repair_attempts

    async def plan(self, request: TripPlanRequest, collection: CollectionResult) -> TripPlan:
        """生成完整旅行计划。

        Args:
            request: 用户规划请求。
            collection: 真实候选数据（景点/酒店/天气）。

        Returns:
            注入天气/预算/地图地址的 TripPlan。

        Raises:
            LLMUnavailableError: LLM provider 不可用。
            LLMOutputError: 校验+修复后仍不符合契约。
        """
        package = self._build_candidate_package(request, collection)
        draft = await self._generate_draft(package, request, collection)
        return await self._finalize(draft, request, collection)

    def _build_candidate_package(
        self,
        request: TripPlanRequest,
        collection: CollectionResult,
    ) -> str:
        """把用户需求 + 真实候选集 + 天气打包为 JSON 文本。"""
        attractions_payload = [
            {
                "poi_id": item.poi_id,
                "name": item.name,
                "address": item.address,
                "location": {
                    "longitude": item.location.longitude,
                    "latitude": item.location.latitude,
                },
                "category": item.category,
                "rating": item.rating,
            }
            for item in collection.attractions
        ]
        hotels_payload = [
            {
                "poi_id": item.poi_id,
                "name": item.name,
                "address": item.address,
                "location": (
                    {"longitude": item.location.longitude, "latitude": item.location.latitude}
                    if item.location is not None
                    else None
                ),
                "type": item.type,
                "rating": item.rating,
                "price_range": item.price_range,
            }
            for item in collection.hotels
        ]
        weather_payload = [
            {
                "date": item.date,
                "day_weather": item.day_weather,
                "night_weather": item.night_weather,
                "day_temp": item.day_temp,
                "night_temp": item.night_temp,
            }
            for item in collection.weather
        ]
        return json.dumps(
            {
                "request": {
                    "city": request.city,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                    "days": request.days,
                    "preferences": request.preferences,
                    "budget": request.budget,
                    "transportation": request.transportation,
                    "accommodation": request.accommodation,
                },
                "attractions": attractions_payload,
                "hotels": hotels_payload,
                "weather": weather_payload,
            },
            ensure_ascii=False,
        )

    async def _generate_draft(
        self,
        package: str,
        request: TripPlanRequest,
        collection: CollectionResult,
    ) -> TripPlanDraft:
        """执行生成：先结构化输出，失败回退文本 JSON + 修复链（≤2 次）。"""
        repair_feedback = ""
        for attempt in range(self._max_repair_attempts + 1):
            user_input = build_user_package(request.city, request.days, package)
            if repair_feedback:
                user_input = (
                    f"{user_input}\n\n{PLANNER_REPAIR_PROMPT_V1}\n校验错误：{repair_feedback}"
                )
            if attempt == 0 and self._llm.structured_supported is not False:
                try:
                    draft = await self._llm.complete_structured(
                        PLANNER_SYSTEM_PROMPT_V1,
                        user_input,
                        TripPlanDraft,
                    )
                    return self._validate_and_reconcile(draft, request, collection)
                except StructuredOutputNotSupported as exc:
                    self._llm.mark_structured_unsupported()
                    repair_feedback = f"结构化输出不可用，请直接输出纯 JSON：{exc}"
                except LLMUnavailableError:
                    raise
                except (PlanValidationError, ValidationError, ValueError) as exc:
                    repair_feedback = str(exc)
            else:
                try:
                    raw_output = await self._llm.complete_text(PLANNER_SYSTEM_PROMPT_V1, user_input)
                    draft = self._parse_draft(raw_output)
                    return self._validate_and_reconcile(draft, request, collection)
                except LLMUnavailableError:
                    raise
                except (PlanValidationError, LLMOutputError, ValidationError, ValueError) as exc:
                    repair_feedback = str(exc)
            logger.warning(
                "Planner 第 %s 次生成未通过校验，进入修复: %s",
                attempt + 1,
                repair_feedback,
            )
        raise LLMOutputError("生成计划失败，请稍后重试")

    @staticmethod
    def _parse_draft(raw_output: str) -> TripPlanDraft:
        """从文本中提取 JSON 并解析为 TripPlanDraft。"""
        cleaned = raw_output.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise PlanValidationError(f"输出不是合法 JSON: {exc}") from exc
        try:
            return TripPlanDraft.model_validate(payload)
        except ValidationError as exc:
            raise PlanValidationError(f"JSON 不符合契约: {exc}") from exc

    def _validate_and_reconcile(
        self,
        draft: TripPlanDraft,
        request: TripPlanRequest,
        collection: CollectionResult,
    ) -> TripPlanDraft:
        """业务校验 + 候选一致性：景点/酒店必须来自真实候选，poi_id 原样引用。"""
        if _normalize_city(draft.city) != _normalize_city(request.city):
            raise PlanValidationError(f"城市({draft.city})与请求城市({request.city})不一致")
        if len(draft.days) != request.days:
            raise PlanValidationError(f"天数({len(draft.days)})与请求({request.days})不一致")

        expected_dates = [
            (request.start_date + timedelta(days=offset)).isoformat()
            for offset in range(request.days)
        ]
        attraction_by_id = {item.poi_id: item for item in collection.attractions}
        hotel_by_id = {item.poi_id: item for item in collection.hotels}

        reconciled_days: list[DayPlan] = []
        for day_index, day in enumerate(draft.days):
            if day.day_index != day_index:
                raise PlanValidationError(f"第{day_index + 1}天 day_index 不连续({day.day_index})")
            if day.date != expected_dates[day_index]:
                raise PlanValidationError(
                    f"第{day_index + 1}天日期({day.date})与请求日期范围不一致"
                )
            reconciled_attractions = [
                self._reconcile_attraction(attraction, attraction_by_id)
                for attraction in day.attractions
            ]
            reconciled_hotel = None
            if day.hotel is not None:
                reconciled_hotel = self._reconcile_hotel(day.hotel, hotel_by_id, collection)
            reconciled_days.append(
                day.model_copy(
                    update={
                        "attractions": reconciled_attractions,
                        "hotel": reconciled_hotel,
                    }
                )
            )
        return draft.model_copy(update={"days": reconciled_days})

    def _reconcile_attraction(
        self,
        attraction: Attraction,
        attraction_by_id: dict[str, AttractionCandidate],
    ) -> Attraction:
        """把 LLM 输出的景点锚定到真实候选（poi_id 优先，其次名称匹配）。"""
        candidate = attraction_by_id.get(attraction.poi_id)
        if candidate is None:
            candidate = _find_candidate_by_name(attraction.name, list(attraction_by_id.values()))
        if candidate is None:
            raise PlanValidationError(
                f"景点「{attraction.name}」不在真实候选列表中（poi_id={attraction.poi_id}）"
            )
        return attraction.model_copy(
            update={
                "poi_id": candidate.poi_id,
                "name": candidate.name,
                "address": candidate.address,
                "location": candidate.location,
                "category": candidate.category or attraction.category,
                "rating": candidate.rating if candidate.rating is not None else attraction.rating,
            }
        )

    def _reconcile_hotel(
        self,
        hotel: Hotel,
        hotel_by_id: dict[str, HotelCandidate],
        collection: CollectionResult,
    ) -> Hotel | None:
        """把 LLM 输出的酒店锚定到真实候选；无酒店候选时移除（不编造）。"""
        candidate = hotel_by_id.get(hotel.poi_id)
        if candidate is None:
            candidate = _find_candidate_by_name(hotel.name, list(hotel_by_id.values()))
        if candidate is None:
            if not collection.hotels:
                return None
            raise PlanValidationError(
                f"酒店「{hotel.name}」不在真实候选列表中（poi_id={hotel.poi_id}）"
            )
        return hotel.model_copy(
            update={
                "poi_id": candidate.poi_id,
                "name": candidate.name,
                "address": candidate.address,
                "location": candidate.location,
                "type": candidate.type or hotel.type,
                "rating": candidate.rating or hotel.rating,
                "price_range": candidate.price_range or hotel.price_range,
            }
        )

    async def _finalize(
        self,
        draft: TripPlanDraft,
        request: TripPlanRequest,
        collection: CollectionResult,
    ) -> TripPlan:
        """注入真实天气/更新时间、重算预算、签发地图 token，完成 TripPlan。"""
        trip_plan = TripPlan(
            city=draft.city,
            start_date=draft.start_date,
            end_date=draft.end_date,
            days=draft.days,
            overall_suggestions=draft.overall_suggestions,
            budget=recalculate_budget(draft, request.budget),
            weather_info=_filter_weather(collection.weather, request),
            weather_updated_at=(
                collection.weather_updated_at.isoformat() if collection.weather_updated_at else None
            ),
            weather_stale=collection.weather_stale,
            notices=list(collection.notices),
        )
        if not collection.hotels and NO_HOTEL_NOTICE not in trip_plan.notices:
            trip_plan.notices.append(NO_HOTEL_NOTICE)

        token = await self._static_map.create_map_token(trip_plan)
        trip_plan.map_image_url = f"/api/trip/static-map/{token}" if token else None
        return trip_plan


def _normalize_city(city: str) -> str:
    """归一化城市名：去除 市/省/自治区 后缀与空白。"""
    normalized = city.strip()
    for suffix in ("壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "市", "省"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _find_candidate_by_name[C: AttractionCandidate | HotelCandidate](
    name: str,
    candidates: list[C],
) -> C | None:
    """按名称归一化匹配候选；完全相同或一方包含另一方且长度≥2 视为命中。"""
    normalized_name = name.strip()
    for candidate in candidates:
        candidate_name = candidate.name.strip()
        if normalized_name == candidate_name:
            return candidate
        shorter, longer = sorted((normalized_name, candidate_name), key=len)
        if len(shorter) >= 2 and shorter in longer:
            return candidate
    return None


def _filter_weather(weather: list[WeatherInfo], request: TripPlanRequest) -> list[WeatherInfo]:
    """只保留行程日期范围内的真实天气数据，绝不补充编造日期。"""
    start = request.start_date.isoformat()
    end = request.end_date.isoformat()
    return [item for item in weather if start <= item.date <= end]
