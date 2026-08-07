"""服务层统一异常定义，保证外部失败路径可感知。"""


class TripMateError(Exception):
    """业务异常基类。"""

    def __init__(self, message: str, *, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AmapError(TripMateError):
    """高德 API 调用失败。"""


class WeatherUnavailableError(TripMateError):
    """天气数据不可用（无缓存且获取失败）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class LLMUnavailableError(TripMateError):
    """LLM 服务不可用（连接/鉴权/超时）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class StructuredOutputNotSupported(TripMateError):
    """Provider 拒绝严格结构化输出（json_schema），需回退文本模式。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class LLMOutputError(TripMateError):
    """LLM 输出经校验/修复后仍不符合契约。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class PlanValidationError(TripMateError):
    """行程校验（候选一致性/业务规则）失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class StaticMapNotFoundError(TripMateError):
    """静态图 token 无效或已过期。"""

    def __init__(self) -> None:
        super().__init__("地图资源不存在或已过期", status_code=404)


class StaticMapRateLimitError(TripMateError):
    """静态图代理触发限流。"""

    def __init__(self) -> None:
        super().__init__("地图请求过于频繁，请稍后再试", status_code=429)


class PlanRateLimitError(TripMateError):
    """行程规划接口触发限流。"""

    def __init__(self) -> None:
        super().__init__("规划请求过于频繁，请稍后再试", status_code=429)


class SharedPlanNotFoundError(TripMateError):
    """分享行程 token 无效或已过期。"""

    def __init__(self) -> None:
        super().__init__("分享行程不存在或已过期", status_code=404)
