/**
 * 前后端共享契约入口。
 *
 * 接口定义由后端 Pydantic 模型自动生成，见 ./contracts.generated.ts。
 * 后端模型变更后必须重新生成：
 *   cd backend && uv run python scripts/export_schemas.py
 *   cd frontend && npm run generate:contracts
 * CI 会重新生成并校验漂移，禁止手工修改 contracts.generated.ts。
 */

export type {
  Attraction,
  Budget,
  DayPlan,
  Hotel,
  Location,
  TripPlan,
  TripPlanDraft,
  TripPlanRequest,
  WeatherInfo,
} from './contracts.generated'

/**
 * 统一响应信封。泛型无法经 JSON Schema 表达，手工维护（成本仅数行）。
 */
export interface ApiEnvelope<T> {
  code: number
  data: T | null
  message: string
}

/**
 * 按天配色的图例色板，需与后端 app/services/static_map_service.py DAY_COLORS 保持同步。
 */
export const DAY_COLORS: string[] = [
  '#1E90FF',
  '#FF8C00',
  '#32CD32',
  '#DA70D6',
  '#20B2AA',
  '#FF69B4',
  '#8A2BE2',
  '#CD853F',
  '#5F9EA0',
  '#DC143C',
]
