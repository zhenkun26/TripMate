"""高德 Web 服务 REST 客户端（POI 搜索 / 天气 / 静态图），带超时与重试。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.services.errors import AmapError

logger = logging.getLogger(__name__)

AMAP_API_BASE_URL = "https://restapi.amap.com/v3"
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = (0.5, 1.0)


class AmapClient:
    """封装高德 REST 调用；外部失败统一抛出 AmapError，禁止静默吞异常。"""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 10.0,
        max_retries: int = MAX_RETRIES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=AMAP_API_BASE_URL,
            timeout=timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        """释放底层连接。"""
        await self._client.aclose()

    async def search_pois(self, city: str, keywords: list[str]) -> list[dict[str, Any]]:
        """文本检索 POI（支持 '|' 多关键词，如 博物馆|历史遗迹）。

        Raises:
            AmapError: 请求失败或返回 status=0 时。
        """
        params = {
            "key": self._api_key,
            "keywords": "|".join(keywords),
            "city": city,
            "citylimit": "true",
            "offset": "25",
            "page": "1",
            "extensions": "base",
        }
        payload = await self._get_json("place/text", params)
        pois = payload.get("pois")
        if not isinstance(pois, list):
            raise AmapError("高德 POI 响应缺少 pois 字段", status_code=502)
        return pois

    async def get_weather(self, adcode: str) -> dict[str, Any]:
        """查询实时天气与未来 3 天预报（extensions=all）。

        Returns:
            原始响应 dict，含 lives/forecasts。
        """
        params = {"key": self._api_key, "city": adcode, "extensions": "all"}
        return await self._get_json("weather/weatherInfo", params)

    async def fetch_static_map(self, params: dict[str, str]) -> bytes:
        """按参数请求高德静态图，返回 PNG 字节。"""
        request_params = {"key": self._api_key, **params}
        try:
            response = await self._request_with_retry("GET", "staticmap", request_params)
        except AmapError:
            raise
        except Exception as exc:
            raise AmapError(f"静态图请求失败: {exc}", status_code=502) from exc
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            raise AmapError("静态图请求被拒绝(检查 key/参数)", status_code=502)
        return response.content

    async def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        response = await self._request_with_retry("GET", path, params)
        try:
            raw_payload: object = response.json()
        except ValueError as exc:
            raise AmapError(f"高德响应不是合法 JSON: {exc}", status_code=502) from exc
        if not isinstance(raw_payload, dict):
            raise AmapError("高德响应结构异常: 顶层不是 JSON 对象", status_code=502)
        payload: dict[str, Any] = raw_payload
        if payload.get("status") != "1":
            info = str(payload.get("info", "未知错误"))
            infocode = str(payload.get("infocode", ""))
            raise AmapError(f"高德接口返回错误[{infocode}]: {info}", status_code=502)
        return payload

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        params: dict[str, str],
    ) -> httpx.Response:
        last_exception: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(method, path, params=params)
                if response.status_code < 500:
                    return response
                last_exception = AmapError(
                    f"高德服务端错误 HTTP {response.status_code}",
                    status_code=502,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exception = exc
            if attempt < self._max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt])
        assert last_exception is not None
        raise AmapError(
            f"高德请求失败(重试{self._max_retries}次后): {last_exception}",
            status_code=502,
        )
