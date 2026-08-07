# TripMate 智能旅行助手

TripMate（智能旅行助手）是一款基于「真实数据采集 + 一次 LLM 生成 + 静态图代理 + 一键分享」闭环的
旅行规划应用（MVP）。用户提交目的地、日期、偏好与预算后，系统基于高德开放平台的真实 POI 与天气数据
生成完整行程，并支持生成品牌分享图，作为传播与获客入口。

## 功能特性

- **行程规划**：PlannerAgent 一次调用完成「整体粗排 → 每日细化」双规划；结构化输出 + Pydantic 校验
  + 修复重试（上限 2 次）；景点与酒店强制来自真实候选数据（`poi_id` 原样引用），禁止编造。
- **真实数据采集**：高德 POI 搜索、天气查询、静态图，三路并行采集；Redis 共享缓存（天气 4h、
  POI 48h、静态图按 token 缓存），Redis 不可用时自动绕过直调，缓存仅作为优化层。
- **预算计算**：门票 / 酒店 / 交通三类明细；门票总额由后端基于结构化票价精确重算，金额使用整数元
  （固定精度），酒店与交通按预算档位锚点表估算。
- **静态地图代理**：后端持有高德 Key，通过不透明 token 返回同源图片；前端零地图代码，失败时自动
  隐藏地图区块，不影响其余内容。
- **品牌分享**：一键将行程（含地图、预算与天气时间戳）生成为带品牌水印的 PNG 分享图。
- **多 LLM 提供商适配**：默认 DeepSeek，支持切换任意 OpenAI 兼容端点（Qwen / OpenAI 等），切换
  不改变输出契约；密钥仅存放于 `.env`，不写入代码仓库。

## 环境要求

| 依赖 | 版本要求 |
| --- | --- |
| Python | 3.13+ |
| uv | 0.11+ |
| Node.js | 24+ |
| npm | 11+ |
| Redis | 本地 `redis-server` |

## 快速开始

### 1. 启动 Redis

```bash
redis-server
```

### 2. 配置并启动后端

```bash
cd backend
cp .env.example .env      # 填写 AMAP_API_KEY 与 LLM_API_KEY
uv sync                   # 首次安装依赖（需要联网）
uv run uvicorn app.api.main:app --reload --port 8000
```

健康检查：`GET http://127.0.0.1:8000/api/health`（返回 Redis 可用状态）。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 。前端已配置 `/api` 代理至 `http://localhost:8000`。

## API Key 获取

- **高德开放平台**：访问 https://console.amap.com/dev/key/app ，创建「Web 服务」类型 Key，填入
  `AMAP_API_KEY`。
- **LLM 服务**：默认 DeepSeek（`LLM_BASE_URL=https://api.deepseek.com`，
  `LLM_MODEL=deepseek-chat`）；可在 `.env` 中切换 Qwen / OpenAI 等任意 OpenAI 兼容端点，
  业务代码无需修改。

密钥仅存放于 `backend/.env`（已被 `.gitignore` 忽略），严禁提交至版本库。

## 环境变量说明

| 变量 | 说明 | 默认值 | 必填 |
| --- | --- | --- | --- |
| `AMAP_API_KEY` | 高德 Web 服务 Key | 空 | 是（未配置时规划接口返回明确错误） |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 | `https://api.deepseek.com` | 是 |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` | 是 |
| `LLM_API_KEY` | LLM 服务密钥 | 空 | 是 |
| `LLM_TEMPERATURE` | 行程生成采样温度 | `0.3` | 否 |
| `REDIS_URL` | Redis 连接串 | `redis://127.0.0.1:6379/0` | 否 |

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/trip/plan` | 生成旅行计划（统一响应信封 `{code, data, message}`） |
| `GET` | `/api/trip/static-map/{token}` | 静态图代理，返回 PNG（图片缓存 + 单 IP 限流） |
| `GET` | `/api/health` | 健康检查，包含 Redis 可用状态 |

## 质量保障

```bash
cd backend
uv run pytest --cov=app --cov-report=term -q   # 单元/集成测试 + 覆盖率
uv run ruff check app tests                    # 代码规范检查
uv run mypy app tests --strict                 # 全量类型检查

cd frontend
npm run build                                  # vue-tsc 类型检查 + vite 构建
```

## 目录结构

```text
backend/
  app/
    api/            FastAPI 路由与统一错误处理
    models/         Pydantic 数据契约（与前端 TypeScript 一一对应）
    services/       高德客户端、候选集、采集编排、缓存、预算、静态图代理
    agents/         LLMClient（多 provider 适配）与 PlannerAgent
    config/         pydantic-settings 配置
  tests/            pytest 单元/集成测试（mock 外部依赖）
frontend/
  src/
    views/          Home 表单 / Result 结果页
    components/     预算、每日行程、天气、静态图与图例
    services/       axios 封装与本地存储
    types/          TypeScript 契约与图例色板
    utils/          格式化工具
openspec/           OpenSpec 规划产物（proposal / specs / design / tasks）
```

## 数据契约与安全说明

- 金额均为非负整数（元），门票总额由后端精确重算，禁止浮点参与金额运算。
- 行程中的景点与酒店必须来自高德真实候选；后端强制校验并兜底锚定，杜绝 LLM 编造。
- 天气仅展示高德接口实际返回的日期（今日及未来 3 天），缺失日期展示「该日期暂无预报」，
  不补充任何编造数据。
- 静态图由后端代理：不透明 token + Redis 参数/图片缓存 + 单 IP 限流；高德 Key 不落地前端。
- 外部服务调用失败必须可感知：明确报错（4xx/5xx 统一信封）或降级提示，禁止静默吞异常。

## 已知限制

- 餐饮规划、行程编辑、PDF 导出、交互地图 SDK、Unsplash 图片服务、MCP server 不在 MVP 范围内。
- 静态图跨天连接线使用浅色细线（高德静态图不支持虚线参数时的确定性降级）；酒店标记不上图
  （渲染密度不可控且无法冒烟验证）。
- Redis 在进程启动时探测：若启动时不可用，本进程将全程绕过缓存；Redis 恢复后需重启后端以重新启用。
- LLM 严格结构化输出（json_schema）若不被提供商支持，将自动回退 prompt + JSON 解析 + 修复链
  （上限 2 次），功能不受影响。
- 用户账号与行程持久化、真实预订支付不在 MVP 范围内。

## 版权与声明

本项目仅用于学习与演示；行程、预算与天气信息仅供参考，出行前请以官方最新信息为准。
