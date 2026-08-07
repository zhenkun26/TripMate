"""数据模型单元测试：坐标/评分/票价校验、温度解析、请求校验。"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    Attraction,
    Budget,
    Location,
    TripPlanRequest,
    WeatherInfo,
)
from tests.conftest import make_attraction


def test_should_accept_valid_location_coordinates() -> None:
    location = Location(longitude=180.0, latitude=90.0)
    assert location.longitude == 180.0
    assert location.latitude == 90.0


@pytest.mark.parametrize(
    ("longitude", "latitude"),
    [(-180.1, 0.0), (0.0, 90.1), (181.0, 0.0), (0.0, -91.0)],
)
def test_should_reject_out_of_range_coordinates(longitude: float, latitude: float) -> None:
    with pytest.raises(ValidationError):
        Location(longitude=longitude, latitude=latitude)


@pytest.mark.parametrize("rating", [-0.1, 5.1, 6.0])
def test_should_reject_out_of_range_rating(rating: float) -> None:
    with pytest.raises(ValidationError):
        make_attraction(rating=rating)


@pytest.mark.parametrize("ticket_price", [-1, 10001])
def test_should_reject_out_of_range_ticket_price(ticket_price: int) -> None:
    with pytest.raises(ValidationError):
        make_attraction(ticket_price=ticket_price)


def test_should_parse_temperature_string_to_int() -> None:
    weather = WeatherInfo.model_validate(
        {
            "date": "2026-08-07",
            "day_weather": "晴",
            "night_weather": "多云",
            "day_temp": "16°C",
            "night_temp": "12℃",
        }
    )
    assert weather.day_temp == 16
    assert weather.night_temp == 12


def test_should_reject_unparseable_temperature() -> None:
    with pytest.raises(ValidationError):
        WeatherInfo.model_validate(
            {
                "date": "2026-08-07",
                "day_weather": "晴",
                "night_weather": "多云",
                "day_temp": "hot",
                "night_temp": 12,
            }
        )


def test_should_accept_int_temperature_without_parsing() -> None:
    weather = WeatherInfo(
        date="2026-08-07",
        day_weather="晴",
        night_weather="多云",
        day_temp=28,
        night_temp=20,
    )
    assert weather.day_temp == 28


def test_should_require_poi_id_on_attraction() -> None:
    with pytest.raises(ValidationError):
        Attraction(
            name="故宫",
            address="北京市",
            location=Location(longitude=116.397, latitude=39.909),
            visit_duration=120,
            poi_id="",
        )


def test_should_validate_request_days_match_date_range() -> None:
    with pytest.raises(ValidationError):
        TripPlanRequest(
            city="北京",
            start_date=date(2026, 8, 7),
            end_date=date(2026, 8, 10),
            days=2,
            preferences="历史文化",
            budget="舒适型",
            transportation="公共交通",
            accommodation="舒适型酒店",
        )


def test_should_reject_end_date_before_start_date() -> None:
    with pytest.raises(ValidationError):
        TripPlanRequest(
            city="北京",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 8),
            days=3,
            preferences="历史文化",
            budget="舒适型",
            transportation="公共交通",
            accommodation="舒适型酒店",
        )


def test_should_reject_negative_budget_amounts() -> None:
    with pytest.raises(ValidationError):
        Budget(total_attractions=-1)


def test_should_reject_attraction_list_out_of_spec_range() -> None:
    from app.models.schemas import DayPlan

    with pytest.raises(ValidationError):
        DayPlan(
            date="2026-08-07",
            day_index=0,
            attractions=[make_attraction()],
        )
