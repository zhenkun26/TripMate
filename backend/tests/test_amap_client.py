"""高德客户端单元测试：正常响应、status=0、超时重试、静态图错误。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
import pytest

from app.services.amap_client import AmapClient
from app.services.errors import AmapError


def _client_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AmapClient:
    return AmapClient(api_key="test-key", transport=httpx.MockTransport(handler), max_retries=2)


@pytest.mark.asyncio
async def test_search_pois_should_return_pois_from_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "1", "pois": [{"id": "P1", "name": "故宫"}]})

    client = _client_with_handler(handler)
    pois = await client.search_pois("北京", ["博物馆"])
    assert pois == [{"id": "P1", "name": "故宫"}]
    await client.aclose()


@pytest.mark.asyncio
async def test_search_pois_should_raise_on_status_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "0", "info": "INVALID_USER_KEY", "infocode": "10001"},
        )

    client = _client_with_handler(handler)
    with pytest.raises(AmapError, match="INVALID_USER_KEY"):
        await client.search_pois("北京", ["景点"])
    await client.aclose()


@pytest.mark.asyncio
async def test_should_retry_transport_error_then_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, json={"status": "1", "pois": [{"id": "P1"}]})

    async def fast_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    client = _client_with_handler(handler)
    pois = await client.search_pois("北京", ["景点"])
    assert pois == [{"id": "P1"}]
    assert attempts == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_should_raise_after_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset")

    async def fast_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    client = _client_with_handler(handler)
    with pytest.raises(AmapError, match="重试"):
        await client.search_pois("北京", ["景点"])
    await client.aclose()


@pytest.mark.asyncio
async def test_should_retry_on_five_hundred(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, json={"status": "1", "pois": []})

    async def fast_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    client = _client_with_handler(handler)
    assert await client.search_pois("北京", ["景点"]) == []
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_static_map_should_return_png_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x89PNG-fake", headers={"content-type": "image/png"})

    client = _client_with_handler(handler)
    image = await client.fetch_static_map({"location": "116.3,39.9", "size": "750x400"})
    assert image == b"\x89PNG-fake"
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_static_map_should_raise_when_returns_json_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "0", "info": "error"},
            headers={"content-type": "application/json"},
        )

    client = _client_with_handler(handler)
    with pytest.raises(AmapError, match="静态图"):
        await client.fetch_static_map({"location": "116.3,39.9"})
    await client.aclose()
