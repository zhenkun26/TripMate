"""预算计算：门票精确重算，酒店/交通按锚点表估算；金额为整数元（固定精度）。"""

from __future__ import annotations

from app.models.schemas import Budget, TripPlanDraft


class BudgetAnchors:
    """预算档位锚点（元）。"""

    def __init__(
        self,
        *,
        hotel_per_night: int = 300,
        transport_per_day: int = 60,
        ticket_estimate: int = 30,
    ) -> None:
        self.hotel_per_night = hotel_per_night
        self.transport_per_day = transport_per_day
        self.ticket_estimate = ticket_estimate


_BUDGET_ANCHORS: dict[str, BudgetAnchors] = {
    "经济型": BudgetAnchors(),
    "舒适型": BudgetAnchors(hotel_per_night=600, transport_per_day=100, ticket_estimate=60),
    "豪华型": BudgetAnchors(hotel_per_night=1200, transport_per_day=200, ticket_estimate=120),
}


def normalize_budget_tier(budget_tier: str) -> str:
    """把任意预算档位文本归一到三档，无法识别时默认舒适型。"""
    text = budget_tier.strip()
    if "经济" in text:
        return "经济型"
    if "豪华" in text or "高端" in text:
        return "豪华型"
    return "舒适型"


def recalculate_budget(draft: TripPlanDraft, budget_tier: str) -> Budget:
    """基于行程结构化数据重算三类预算与总额（门票精确求和，缺失按档位估算）。

    Args:
        draft: 已校验的行程草稿。
        budget_tier: 用户预算档位（经济型/舒适型/豪华型）。

    Returns:
        重算后的 Budget。
    """
    anchors = _BUDGET_ANCHORS[normalize_budget_tier(budget_tier)]
    total_attractions = sum(
        attraction.ticket_price if attraction.ticket_price > 0 else anchors.ticket_estimate
        for day in draft.days
        for attraction in day.attractions
    )
    total_hotels = sum(day.hotel.estimated_cost for day in draft.days if day.hotel is not None)
    if total_hotels == 0:
        hotel_nights = max(len(draft.days) - 1, 1)
        total_hotels = anchors.hotel_per_night * hotel_nights
    total_transportation = anchors.transport_per_day * len(draft.days)
    total = total_attractions + total_hotels + total_transportation
    return Budget(
        total_attractions=total_attractions,
        total_hotels=total_hotels,
        total_transportation=total_transportation,
        total=total,
    )
