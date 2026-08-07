"""预算计算单元测试：精确重算 + 边界。"""

from __future__ import annotations

from app.services.budget_service import normalize_budget_tier, recalculate_budget
from tests.conftest import make_draft, make_request


def test_should_recalculate_attraction_total_exactly() -> None:
    draft = make_draft()
    budget = recalculate_budget(draft, "舒适型")
    assert budget.total_attractions == 3 * (50 + 30)


def test_should_estimate_missing_ticket_prices_by_tier() -> None:
    draft = make_draft()
    draft.days[0].attractions[0].ticket_price = 0
    budget = recalculate_budget(draft, "舒适型")
    expected = 60 + 30 + 50 + 30 + 50 + 30
    assert budget.total_attractions == expected


def test_should_compute_hotels_and_transportation_from_anchors() -> None:
    draft = make_draft()
    for day in draft.days:
        if day.hotel is not None:
            day.hotel.estimated_cost = 0
    budget = recalculate_budget(draft, "经济型")
    assert budget.total_hotels == 600
    assert budget.total_transportation == 180
    assert budget.total == (
        budget.total_attractions + budget.total_hotels + budget.total_transportation
    )


def test_should_use_single_day_trip_for_boundary() -> None:
    request = make_request(days=1)
    draft = make_draft(days_count=1)
    draft.days[0].hotel = None
    budget = recalculate_budget(draft, request.budget)
    assert budget.total_hotels == 600
    assert budget.total_transportation == 100


def test_should_normalize_budget_tier() -> None:
    assert normalize_budget_tier("经济型酒店") == "经济型"
    assert normalize_budget_tier("豪华") == "豪华型"
    assert normalize_budget_tier("随便") == "舒适型"
