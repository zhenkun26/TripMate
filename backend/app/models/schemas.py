"""TripMate 前后端共享的数据契约。

所有金额字段均为非负整数（元），采用固定精度整数运算；
天气温度字段允许接收 "16°C" 形式的字符串并在解析时归一化为整数。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class Location(BaseModel):
    """经纬度坐标。"""

    longitude: float = Field(..., ge=-180, le=180, description="经度")
    latitude: float = Field(..., ge=-90, le=90, description="纬度")


class Attraction(BaseModel):
    """景点信息（来自高德真实候选数据）。"""

    name: str = Field(..., min_length=1, max_length=100, description="景点名称")
    address: str = Field(default="", max_length=200, description="地址")
    location: Location = Field(..., description="经纬度坐标")
    visit_duration: int = Field(..., gt=0, le=1440, description="建议游览时间(分钟)")
    description: str = Field(default="", max_length=500, description="景点描述")
    category: str | None = Field(default=None, max_length=50, description="景点类别")
    rating: float | None = Field(default=None, ge=0, le=5, description="评分")
    image_url: str | None = Field(default=None, max_length=500, description="图片URL")
    ticket_price: int = Field(default=0, ge=0, le=10000, description="门票价格(元)")
    poi_id: str = Field(..., min_length=1, max_length=64, description="高德 poi_id")


class Hotel(BaseModel):
    """酒店信息（来自高德真实候选数据）。"""

    name: str = Field(..., min_length=1, max_length=100, description="酒店名称")
    address: str = Field(default="", max_length=200, description="酒店地址")
    location: Location | None = Field(default=None, description="酒店位置")
    price_range: str = Field(default="", max_length=100, description="价格范围")
    rating: str = Field(default="", max_length=20, description="评分")
    distance: str = Field(default="", max_length=50, description="距离景点距离")
    type: str = Field(default="", max_length=50, description="酒店类型")
    estimated_cost: int = Field(default=0, ge=0, le=100000, description="预估费用(元/晚)")
    poi_id: str = Field(..., min_length=1, max_length=64, description="高德 poi_id")


class Budget(BaseModel):
    """预算明细（门票/酒店/交通三类，金额为非负整数元）。"""

    total_attractions: int = Field(default=0, ge=0, description="景点门票总费用(元)")
    total_hotels: int = Field(default=0, ge=0, description="酒店总费用(元)")
    total_transportation: int = Field(default=0, ge=0, description="交通总费用(元)")
    total: int = Field(default=0, ge=0, description="预估总费用(元)")


class WeatherInfo(BaseModel):
    """单日天气信息（仅来自高德天气接口实际返回的数据）。"""

    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", max_length=50, description="白天天气")
    night_weather: str = Field(default="", max_length=50, description="夜间天气")
    day_temp: int = Field(..., ge=-60, le=60, description="白天温度(摄氏度)")
    night_temp: int = Field(..., ge=-60, le=60, description="夜间温度(摄氏度)")
    wind_direction: str = Field(default="", max_length=50, description="风向")
    wind_power: str = Field(default="", max_length=50, description="风力")

    @field_validator("day_temp", "night_temp", mode="before")
    @classmethod
    def parse_temperature(cls, value: object) -> object:
        """解析温度字符串（"16°C"/"16℃" -> 16），无法解析时报错而非静默归零。"""
        if not isinstance(value, str):
            return value
        normalized = value.replace("°C", "").replace("℃", "").replace("°", "").strip()
        try:
            return int(normalized)
        except ValueError as exc:
            raise ValueError(f"无法解析温度值: {value!r}") from exc


class DayPlan(BaseModel):
    """单日行程（每天 2-3 个景点）。"""

    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="日期 YYYY-MM-DD")
    day_index: int = Field(..., ge=0, le=30, description="第几天(从0开始)")
    description: str = Field(default="", max_length=1000, description="当日行程描述")
    transportation: str = Field(default="", max_length=100, description="当日交通方式")
    accommodation: str = Field(default="", max_length=100, description="当日住宿安排")
    hotel: Hotel | None = Field(default=None, description="酒店信息")
    attractions: list[Attraction] = Field(
        default_factory=list,
        min_length=2,
        max_length=3,
        description="景点列表(2-3个)",
    )


class TripPlanDraft(BaseModel):
    """PlannerAgent 输出的原始行程草稿（未注入天气/地图等派生字段）。"""

    city: str = Field(..., min_length=1, max_length=50, description="目的地城市")
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="开始日期")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="结束日期")
    days: list[DayPlan] = Field(..., min_length=1, max_length=14, description="每日行程")
    overall_suggestions: str = Field(default="", max_length=2000, description="总体建议")
    budget: Budget | None = Field(default=None, description="预算信息(后端将重算)")


class TripPlan(TripPlanDraft):
    """对外返回的完整旅行计划（含派生字段与降级信息）。"""

    weather_info: list[WeatherInfo] = Field(default_factory=list, description="天气信息")
    weather_updated_at: str | None = Field(default=None, description="天气数据更新时间(ISO8601)")
    weather_stale: bool = Field(default=False, description="天气数据是否延迟")
    map_image_url: str | None = Field(default=None, description="静态地图代理地址")
    notices: list[str] = Field(default_factory=list, description="降级/提示信息")


class TripPlanRequest(BaseModel):
    """用户规划请求。"""

    city: str = Field(..., min_length=1, max_length=50, description="目的地城市")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    days: int = Field(..., ge=1, le=14, description="旅行天数")
    preferences: str = Field(..., min_length=1, max_length=100, description="旅行偏好")
    budget: str = Field(..., min_length=1, max_length=20, description="预算档位")
    transportation: str = Field(..., min_length=1, max_length=20, description="交通方式")
    accommodation: str = Field(..., min_length=1, max_length=20, description="住宿类型")

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, value: date, info: ValidationInfo) -> date:
        """确保结束日期不早于开始日期。"""
        start_date = info.data.get("start_date")
        if start_date is not None and value < start_date:
            raise ValueError("结束日期不能早于开始日期")
        return value

    @model_validator(mode="after")
    def validate_days_match_date_range(self) -> TripPlanRequest:
        """确保旅行天数与日期范围一致。"""
        expected_days = (self.end_date - self.start_date).days + 1
        if self.days != expected_days:
            raise ValueError(f"旅行天数({self.days})与日期范围({expected_days}天)不一致")
        return self


class ApiEnvelope[T](BaseModel):
    """统一响应信封。"""

    code: int = Field(..., description="0 表示成功，非 0 表示错误码")
    data: T | None = Field(default=None, description="业务数据")
    message: str = Field(default="success", description="提示信息")
