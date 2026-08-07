"""应用配置：全部通过环境变量 / .env 注入，密钥不入库。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中管理后端运行所需的全部配置项。

    Args:
        amap_api_key: 高德 Web 服务 Key（必填，缺失时外部调用会明确报错）。
        llm_base_url: OpenAI 兼容接口的 base_url。
        llm_model: 模型名称。
        llm_api_key: LLM 提供商 API Key。
        llm_temperature: 行程生成采样温度。
        llm_timeout_seconds: LLM 单次调用超时。
        redis_url: Redis 连接串。
        static_map_size: 静态图尺寸 "宽x高"。
        static_map_token_ttl_seconds: 静态图 token/图片缓存 TTL。
        static_map_rate_limit_per_minute: 静态图代理单 IP 每分钟限流次数。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    amap_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""
    llm_temperature: float = 0.3
    llm_timeout_seconds: float = 120.0
    redis_url: str = "redis://127.0.0.1:6379/0"
    static_map_size: str = "750x400"
    static_map_token_ttl_seconds: int = 24 * 60 * 60
    static_map_rate_limit_per_minute: int = 60


@lru_cache
def get_settings() -> Settings:
    """返回缓存的全局配置实例。"""
    return Settings()
