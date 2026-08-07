"""LLMClient：OpenAI 兼容多 provider 适配（DeepSeek/Qwen/OpenAI），基于 openai-agents SDK。"""

from __future__ import annotations

import logging
import time
from typing import Any, TypeVar

import httpx
from agents import Agent, ModelSettings, Runner, set_default_openai_client, set_tracing_disabled
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel

from app.services.errors import LLMOutputError, LLMUnavailableError, StructuredOutputNotSupported

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """OpenAI 兼容接口客户端；base_url/model/api_key 全配置化，切换 provider 不改契约。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.3,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._structured_supported: bool | None = None
        self._openai_client = AsyncOpenAI(
            base_url=self._base_url,
            # openai SDK 构造时强制要求 key；真实调用前会校验 _api_key 非空
            api_key=self._api_key or "not-configured",
            timeout=self._timeout_seconds,
        )
        set_default_openai_client(self._openai_client, use_for_tracing=False)
        set_tracing_disabled(True)

    @property
    def structured_supported(self) -> bool | None:
        """结构化输出支持状态：None=未探测，True/False=探测结果。"""
        return self._structured_supported

    def mark_structured_unsupported(self) -> None:
        """记录当前 provider 不支持严格结构化输出，后续直接走文本回退。"""
        self._structured_supported = False
        logger.info(
            "LLM provider 不支持严格结构化输出，回退 prompt+JSON 修复链: %s",
            self._base_url,
        )

    async def complete_structured(
        self,
        instructions: str,
        user_input: str,
        output_type: type[T],
    ) -> T:
        """使用 openai-agents SDK 的 structured output 生成并校验。

        Args:
            instructions: 系统提示词。
            user_input: 用户侧数据包文本。
            output_type: Pydantic 输出模型。

        Returns:
            校验通过的模型实例。

        Raises:
            StructuredOutputNotSupported: provider 拒绝 json_schema。
            LLMUnavailableError: 网络/鉴权/限流等 provider 不可用错误。
            LLMOutputError: SDK 内部修复耗尽仍未产出合法结果。
        """
        if not self._api_key:
            raise LLMUnavailableError("未配置 LLM_API_KEY")
        agent = Agent(
            name="planner",
            instructions=instructions,
            model=self._model,
            output_type=output_type,
            model_settings=ModelSettings(temperature=self._temperature),
        )
        started_at = time.monotonic()
        try:
            result = await Runner.run(agent, input=user_input, max_turns=3)
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc
        self._log_usage("structured", started_at, result)
        output = result.final_output_as(output_type)
        if output is None:
            raise LLMOutputError("LLM 未产出符合契约的结构化结果")
        return output

    async def complete_text(self, instructions: str, user_input: str) -> str:
        """文本模式调用（修复链使用），返回原始文本。

        Args:
            instructions: 系统提示词。
            user_input: 用户侧数据包文本。

        Returns:
            模型输出文本。

        Raises:
            LLMUnavailableError: provider 不可用。
            LLMOutputError: 未返回文本。
        """
        if not self._api_key:
            raise LLMUnavailableError("未配置 LLM_API_KEY")
        agent = Agent(
            name="planner-text",
            instructions=instructions,
            model=self._model,
            model_settings=ModelSettings(temperature=self._temperature),
        )
        started_at = time.monotonic()
        try:
            result = await Runner.run(agent, input=user_input, max_turns=2)
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc
        self._log_usage("text", started_at, result)
        output = result.final_output_as(str)
        if output is None:
            raise LLMOutputError("LLM 未返回文本结果")
        return output

    def _log_usage(self, mode: str, started_at: float, result: Any) -> None:
        """记录单次 LLM 调用的 token 用量与耗时（成本可观测）。"""
        latency_seconds = time.monotonic() - started_at
        usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        logger.info(
            "LLM 调用完成: mode=%s model=%s latency=%.1fs input_tokens=%s output_tokens=%s",
            mode,
            self._model,
            latency_seconds,
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )

    def _map_sdk_error(self, exc: Exception) -> Exception:
        """把 SDK/openai/httpx 异常映射为领域异常，保证失败路径可感知。"""
        if isinstance(exc, OpenAIError):
            status_code = getattr(exc, "status_code", None)
            if status_code == 400:
                logger.warning("LLM 结构化输出被 provider 拒绝(status=400): %s", exc)
                return StructuredOutputNotSupported(str(exc))
            return LLMUnavailableError(f"LLM 服务不可用: {exc}")
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return LLMUnavailableError(f"LLM 网络错误: {exc}")
        logger.warning("LLM 输出生成失败(非连接类): %s", exc)
        return LLMOutputError(f"LLM 输出生成失败: {exc}")
