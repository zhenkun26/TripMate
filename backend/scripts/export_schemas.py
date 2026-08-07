"""导出前后端共享契约为 JSON Schema，供 json-schema-to-typescript 生成 TS 类型。

用法：
    cd backend && uv run python scripts/export_schemas.py
输出：
    frontend/contracts/contracts.json

后端模型变更后必须重新执行本脚本并在前端执行 `npm run generate:contracts`；
CI 会重新生成并做 `git diff --exit-code` 漂移检查。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# 让脚本可直接以文件路径运行（sys.path 默认只含 scripts/ 目录）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel  # noqa: E402

from app.models.schemas import (  # noqa: E402
    Attraction,
    Budget,
    DayPlan,
    Hotel,
    Location,
    TripPlan,
    TripPlanDraft,
    TripPlanRequest,
    WeatherInfo,
)

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "contracts" / "contracts.json"


class ContractBundle(BaseModel):
    """聚合全部共享契约模型，仅用于一次性导出 $defs（不参与运行逻辑）。"""

    location: Location
    attraction: Attraction
    hotel: Hotel
    budget: Budget
    weather_info: WeatherInfo
    day_plan: DayPlan
    trip_plan_draft: TripPlanDraft
    trip_plan: TripPlan
    trip_plan_request: TripPlanRequest


def _normalize_model_schemas(schema: dict[str, Any]) -> None:
    """规范化模型 JSON Schema，使生成的 TS 接口精确对齐后端序列化行为。

    - 把每个模型的 properties 全部标记为 required：后端序列化总是输出全部字段，
      避免「有默认值即可选」的语义把 TS 字段生成为 `field?:`；
    - additionalProperties=false：Pydantic 默认拒绝额外字段，避免生成
      `[k: string]: unknown` 索引签名；
    - 移除属性级 title：避免 json2ts 为每个字段生成 Name/Name1 等噪声别名，
      字段类型内联，仅保留 $defs 级接口与 description 注释。
    """

    def normalize(model_schema: dict[str, Any]) -> None:
        properties = model_schema.get("properties")
        if not isinstance(properties, dict):
            return
        model_schema["required"] = list(properties.keys())
        model_schema["additionalProperties"] = False
        for property_schema in properties.values():
            if isinstance(property_schema, dict):
                property_schema.pop("title", None)

    normalize(schema)
    defs = schema.get("$defs", {})
    for model_schema in defs.values():
        if isinstance(model_schema, dict):
            normalize(model_schema)


def main() -> None:
    schema = ContractBundle.model_json_schema(ref_template="#/$defs/{model}")
    _normalize_model_schemas(schema)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "Contracts"
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"契约已导出: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
