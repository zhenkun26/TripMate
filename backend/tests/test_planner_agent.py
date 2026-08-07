"""PlannerAgent 单元测试：正常/非法JSON/缺字段/越界/修复成败/无酒店/无天气/provider 切换。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import BaseModel

from app.agents.llm_client import LLMClient
from app.agents.planner_agent import NO_HOTEL_NOTICE, PlannerAgent
from app.models.schemas import TripPlanDraft
from app.services.candidate_service import build_attraction_candidates, build_hotel_candidates
from app.services.collection_service import CollectionResult
from app.services.errors import LLMOutputError, PlanValidationError
from app.services.rate_limit import SlidingWindowRateLimiter
from app.services.static_map_service import StaticMapService
from tests.conftest import (
    FakeAmapClient,
    FakeCache,
    make_attraction,
    make_draft,
    make_hotel,
    make_request,
    make_weather,
)


class FakeLLMClient(LLMClient):
    """可编排响应的假 LLM 客户端。"""

    def __init__(self) -> None:
        super().__init__(base_url="https://llm.example.com", api_key="test-key", model="fake-model")
        self.structured_responses: list[TripPlanDraft | Exception] = []
        self.text_responses: list[str | Exception] = []
        self.structured_calls = 0
        self.text_calls = 0

    async def complete_structured[T: BaseModel](
        self,
        instructions: str,
        user_input: str,
        output_type: type[T],
    ) -> T:
        self.structured_calls += 1
        response = (
            self.structured_responses.pop(0)
            if self.structured_responses
            else LLMOutputError("无响应")
        )
        if isinstance(response, Exception):
            raise response
        return cast(T, response)

    async def complete_text(self, instructions: str, user_input: str) -> str:
        self.text_calls += 1
        response = self.text_responses.pop(0) if self.text_responses else LLMOutputError("无响应")
        if isinstance(response, Exception):
            raise response
        return response


def build_collection(
    *,
    weather: bool = True,
    hotels: bool = True,
) -> CollectionResult:
    """构造样例候选集。"""
    slot_index = {"A": 0, "B": 1}
    raw_attractions = [
        {
            "id": f"POI-{day}-{slot}",
            "name": f"景点{day}{slot}",
            "location": f"{116.3 + day + slot_index[slot] / 10},{39.9 + day}",
            "address": f"地址{day}{slot}",
            "type": "风景名胜",
            "rating": "4.6",
            "adcode": "110000",
        }
        for day in range(3)
        for slot in ("A", "B")
    ]
    raw_hotels = [
        {
            "id": f"HOTEL-{day}",
            "name": f"酒店{day}",
            "location": f"116.4,{39.9 + day}",
            "address": f"酒店地址{day}",
            "type": "酒店",
            "rating": "4.5",
            "biz_ext": {"cost": "500"},
        }
        for day in range(3)
    ]
    weather_list = [make_weather()] if weather else []
    return CollectionResult(
        adcode="110000",
        attractions=build_attraction_candidates(raw_attractions),
        hotels=build_hotel_candidates(raw_hotels) if hotels else [],
        weather=weather_list,
        weather_updated_at=datetime(2026, 8, 7, 8, 0, tzinfo=UTC) if weather else None,
        weather_stale=False,
        notices=[],
    )


def build_agent(llm: FakeLLMClient) -> tuple[PlannerAgent, StaticMapService, FakeCache]:
    """装配 PlannerAgent 与共享 FakeCache/静态图服务。"""
    cache = FakeCache()
    amap = FakeAmapClient()
    static_map = StaticMapService(
        cache,
        amap,
        size="750x400",
        token_ttl_seconds=86400,
        rate_limiter=SlidingWindowRateLimiter(60),
    )
    return PlannerAgent(llm, static_map), static_map, cache


@pytest.mark.asyncio
async def test_should_plan_happy_path_with_structured_output() -> None:
    llm = FakeLLMClient()
    llm.structured_responses = [make_draft()]
    agent, _static_map, _cache = build_agent(llm)
    request = make_request()
    collection = build_collection()

    trip_plan = await agent.plan(request, collection)

    assert len(trip_plan.days) == 3
    assert trip_plan.weather_info == collection.weather
    assert trip_plan.map_image_url is not None
    assert trip_plan.budget is not None
    assert trip_plan.budget.total_attractions == 240


@pytest.mark.asyncio
async def test_should_fallback_to_text_and_repair_when_structured_unsupported() -> None:
    llm = FakeLLMClient()
    llm.structured_responses = [PlanValidationError("结构化输出不可用")]
    llm.text_responses = ["这不是 JSON", "```json\n" + make_draft().model_dump_json() + "\n```"]
    agent, _static_map, _cache = build_agent(llm)

    trip_plan = await agent.plan(make_request(), build_collection())

    assert llm.structured_calls == 1
    assert llm.text_calls == 2
    assert len(trip_plan.days) == 3


@pytest.mark.asyncio
async def test_should_repair_when_json_has_too_many_attractions() -> None:
    llm = FakeLLMClient()
    llm.structured_responses = [PlanValidationError("严格模式不可用")]
    invalid_payload = json.loads(make_draft().model_dump_json())
    invalid_payload["days"][0]["attractions"].append(make_attraction(name="多余景点").model_dump())
    llm.text_responses = [
        json.dumps(invalid_payload, ensure_ascii=False),
        make_draft().model_dump_json(),
    ]
    agent, _static_map, _cache = build_agent(llm)

    trip_plan = await agent.plan(make_request(), build_collection())

    assert llm.text_calls == 2
    assert all(len(day.attractions) <= 3 for day in trip_plan.days)


@pytest.mark.asyncio
async def test_should_raise_when_repair_fails_after_max_attempts() -> None:
    llm = FakeLLMClient()
    llm.structured_responses = [PlanValidationError("严格模式不可用")]
    llm.text_responses = ["坏 JSON", "还是坏 JSON", "仍然坏 JSON"]
    agent, _static_map, _cache = build_agent(llm)

    with pytest.raises(LLMOutputError, match="生成计划失败，请稍后重试"):
        await agent.plan(make_request(), build_collection())
    assert llm.text_calls == 2


@pytest.mark.asyncio
async def test_should_reject_fabricated_attraction_and_repair() -> None:
    llm = FakeLLMClient()
    llm.structured_responses = [PlanValidationError("严格模式不可用")]
    fake_payload = json.loads(make_draft().model_dump_json())
    fake_payload["days"][0]["attractions"][0]["poi_id"] = "NOT-IN-CANDIDATES"
    fake_payload["days"][0]["attractions"][0]["name"] = "编造景点"
    llm.text_responses = [
        json.dumps(fake_payload, ensure_ascii=False),
        make_draft().model_dump_json(),
    ]
    agent, _static_map, _cache = build_agent(llm)

    trip_plan = await agent.plan(make_request(), build_collection())

    assert all(
        attraction.poi_id.startswith("POI-")
        for day in trip_plan.days
        for attraction in day.attractions
    )


@pytest.mark.asyncio
async def test_should_remove_hotel_when_no_hotel_candidates() -> None:
    llm = FakeLLMClient()
    draft = make_draft()
    for day in draft.days:
        day.hotel = make_hotel()
    llm.structured_responses = [draft]
    agent, _static_map, _cache = build_agent(llm)
    collection = build_collection(hotels=False)

    trip_plan = await agent.plan(make_request(), collection)

    assert all(day.hotel is None for day in trip_plan.days)
    assert NO_HOTEL_NOTICE in trip_plan.notices


@pytest.mark.asyncio
async def test_should_return_empty_weather_when_weather_unavailable() -> None:
    llm = FakeLLMClient()
    llm.structured_responses = [make_draft()]
    agent, _static_map, _cache = build_agent(llm)
    collection = build_collection(weather=False)

    trip_plan = await agent.plan(make_request(), collection)

    assert trip_plan.weather_info == []
    assert trip_plan.weather_updated_at is None


@pytest.mark.asyncio
async def test_should_use_text_path_when_provider_marked_structured_unsupported() -> None:
    llm = FakeLLMClient()
    llm.mark_structured_unsupported()
    llm.text_responses = [make_draft().model_dump_json()]
    agent, _static_map, _cache = build_agent(llm)

    await agent.plan(make_request(), build_collection())

    assert llm.structured_calls == 0
    assert llm.text_calls == 1


@pytest.mark.asyncio
async def test_should_raise_when_city_mismatch_and_repairs_exhausted() -> None:
    llm = FakeLLMClient()
    llm.structured_responses = [PlanValidationError("严格模式不可用")]
    mismatched = json.loads(make_draft().model_dump_json())
    mismatched["city"] = "上海"
    llm.text_responses = [json.dumps(mismatched, ensure_ascii=False)] * 3
    agent, _static_map, _cache = build_agent(llm)

    with pytest.raises(LLMOutputError):
        await agent.plan(make_request(), build_collection())


@pytest.mark.asyncio
async def test_should_raise_plan_validation_for_unknown_poi_without_repair() -> None:
    llm = FakeLLMClient()
    draft = make_draft()
    draft.days[0].attractions[0].poi_id = "UNKNOWN"
    draft.days[0].attractions[0].name = "编造景点"
    agent, _static_map, _cache = build_agent(llm)

    with pytest.raises(PlanValidationError, match="不在真实候选列表中"):
        agent._validate_and_reconcile(draft, make_request(), build_collection())
