# TripMate 智能旅行助手 / TripMate Smart Travel Assistant

> 一次输入，即刻生成可执行的旅行计划 —— 真实数据、可信预算、品牌分享。
> One input, an actionable itinerary in seconds — real data, trusted budgeting, brand-ready sharing.

## 项目简介 / Product Overview

TripMate 是一款面向个人旅行者的智能行程规划产品。用户提交目的地、日期、旅行偏好与预算档位后，
系统在数秒至十余秒内生成包含每日行程、酒店建议、天气信息、预算明细与静态地图的完整旅行计划，
并支持一键导出品牌分享图，形成「规划 → 出行 → 分享」的完整体验闭环。

TripMate is an intelligent itinerary planning product for individual travelers. After the user
submits a destination, travel dates, preferences, and a budget tier, the system generates a
complete travel plan — daily itinerary, hotel suggestions, weather, budget breakdown, and a static
map — within seconds to tens of seconds, and supports one-click export of a brand share image,
forming a complete "plan → travel → share" experience loop.

### 产品价值 / Product Value

- **真实数据驱动**：行程中的景点与酒店均来自高德开放平台的真实 POI 数据，杜绝编造内容。
  Real data driven: every attraction and hotel in the itinerary comes from authentic Amap POI data —
  no fabricated content.
- **预算可信**：门票总额由后端基于结构化票价精确重算，酒店与交通按预算档位锚点表估算。
  Trusted budgeting: attraction totals are precisely recalculated from structured ticket prices,
  while hotels and transportation follow budget-tier anchor estimates.
- **开箱即用**：本地数条命令即可完整运行，技术栈均为成熟稳定的开源组件。
  Ready to run: a few local commands start the full stack, built entirely on mature open-source
  components.
- **分享传播**：一键生成带品牌水印的分享图，作为传播与获客入口。
  Shareable: one click produces a branded share image, serving as a growth and acquisition entry.

## 核心功能 / Core Features

| 功能 / Feature | 说明 / Description |
| --- | --- |
| 行程规划 / Itinerary Planning | 单次模型调用完成「整体粗排 → 每日细化」双规划，结构化输出 + 契约校验 + 修复重试（上限 2 次）。A single model call completes dual planning (global ordering → daily refinement) with structured output, contract validation, and repair retries (max 2). |
| 真实数据采集 / Real Data Collection | 高德 POI 搜索、天气查询与静态图三路并行采集；Redis 共享缓存（天气 4 小时、POI 48 小时、静态图按 token 缓存）。Amap POI search, weather, and static-map requests are collected in parallel, with Redis shared caching (weather 4h, POI 48h, static maps by token). |
| 预算计算 / Budget Calculation | 门票 / 酒店 / 交通三类明细与预估总额，金额统一为整数元。Itemized ticket / hotel / transportation estimates with integer-yuan precision. |
| 静态地图 / Static Map | 后端持有地图密钥并通过不透明 token 代理生成同源图片，前端零地图代码。The backend holds the map key and proxies same-origin images via opaque tokens; the frontend contains no map code. |
| 天气信息 / Weather | 仅展示服务实际返回的预报日期，缺失日期明确标注，不补充任何编造数据。Only dates actually returned by the weather service are displayed; missing dates are explicitly marked and never fabricated. |
| 品牌分享 / Brand Sharing | 行程（含地图、预算与天气时间戳）一键导出为带品牌水印的 PNG 分享图。The itinerary (map, budget, and weather timestamp) is exported as a watermarked PNG share image in one click. |
| 多模型适配 / Multi-Provider LLM | 默认 DeepSeek，可通过配置切换任意 OpenAI 兼容端点（Qwen / OpenAI 等），输出契约保持不变。DeepSeek by default; any OpenAI-compatible endpoint (Qwen / OpenAI, etc.) can be selected via configuration without changing the output contract. |

## 技术架构 / Architecture

| 层次 / Layer | 技术选型 / Technology |
| --- | --- |
| 前端 / Frontend | Vue 3 + TypeScript + Vite + Ant Design Vue + html2canvas |
| 后端 / Backend | FastAPI + Pydantic v2 |
| 智能体 / Agent | openai-agents（PlannerAgent 结构化输出 + 校验 + 修复重试 ≤2） |
| 数据源 / Data Source | 高德开放平台 REST（POI 搜索 / 天气 / 静态图） |
| 缓存 / Cache | Redis（天气 4h、POI 48h、静态图按 token 缓存；不可用时自动绕过直调） |
| 模型服务 / Model Service | OpenAI 兼容接口，默认 DeepSeek |

架构采用前后端分离的单一代码仓库：后端提供统一响应信封的 REST API 并持有全部密钥，
前端通过 `/api` 代理访问。所有外部调用均配置超时与重试，失败路径可感知（明确报错或优雅降级），
Redis 仅作为优化层而非功能依赖。

The repository is a single codebase with a separated frontend and backend: the backend exposes a
REST API with a unified response envelope and holds all secrets, while the frontend accesses it via
the `/api` proxy. Every external call has timeouts and retries with perceptible failure paths
(explicit errors or graceful degradation); Redis is an optimization layer, never a functional
dependency.

## 快速开始 / Quick Start

### 1. 启动 Redis / Start Redis

```bash
redis-server
```

### 2. 配置并启动后端 / Configure and Start the Backend

```bash
cd backend
cp .env.example .env      # 填写 AMAP_API_KEY 与 LLM_API_KEY
uv sync                   # 首次安装依赖（需要联网）
uv run uvicorn app.api.main:app --reload --port 8000
```

健康检查：`GET http://127.0.0.1:8000/api/health`（返回 Redis 可用状态）。
Health check: `GET http://127.0.0.1:8000/api/health` (reports Redis availability).

### 3. 启动前端 / Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 ，前端已将 `/api` 代理至 `http://localhost:8000`。
Open http://localhost:5173 ; the frontend proxies `/api` to `http://localhost:8000`.

## API Key 获取 / Obtaining API Keys

- **高德开放平台 / Amap Open Platform**：https://console.amap.com/dev/key/app ，创建「Web 服务」
  类型 Key，填入 `AMAP_API_KEY`。
- **LLM 服务 / LLM Service**：默认 DeepSeek；可在 `.env` 中切换 Qwen / OpenAI 等任意
  OpenAI 兼容端点，业务代码无需修改。

密钥仅存放于 `backend/.env`（已被 `.gitignore` 忽略），严禁提交至版本库。
Secrets live only in `backend/.env` (ignored by `.gitignore`) and must never be committed.

## 环境变量说明 / Environment Variables

| 变量 / Variable | 说明 / Description | 默认值 / Default | 必填 / Required |
| --- | --- | --- | --- |
| `AMAP_API_KEY` | 高德 Web 服务 Key / Amap web service key | 空 / empty | 是 / Yes |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 / OpenAI-compatible endpoint | `https://api.deepseek.com` | 是 / Yes |
| `LLM_MODEL` | 模型名称 / Model name | `deepseek-chat` | 是 / Yes |
| `LLM_API_KEY` | LLM 服务密钥 / LLM service key | 空 / empty | 是 / Yes |
| `LLM_TEMPERATURE` | 行程生成采样温度 / Sampling temperature | `0.3` | 否 / No |
| `REDIS_URL` | Redis 连接串 / Redis connection string | `redis://127.0.0.1:6379/0` | 否 / No |

## API 概览 / API Overview

| 方法 / Method | 路径 / Path | 说明 / Description |
| --- | --- | --- |
| `POST` | `/api/trip/plan` | 生成旅行计划，统一响应信封 `{code, data, message}` / Generate a travel plan with a unified response envelope |
| `GET` | `/api/trip/static-map/{token}` | 静态图代理，返回 PNG（图片缓存 + 单 IP 限流）/ Static-map proxy returning PNG (image cache + per-IP rate limit) |
| `GET` | `/api/health` | 健康检查，含 Redis 可用状态 / Health check including Redis availability |

## 质量保障 / Quality Assurance

```bash
cd backend
uv run pytest --cov=app --cov-report=term -q   # 单元/集成测试 + 覆盖率 / tests + coverage
uv run ruff check app tests                    # 代码规范检查 / lint
uv run mypy app tests --strict                 # 全量类型检查 / strict type checking

cd frontend
npm run build                                  # vue-tsc 类型检查 + vite 构建 / type check + build
```

当前状态 / Current status：后端 74 项单元与集成测试，行覆盖率 88%；ruff 零告警；
mypy（strict 模式）全量通过；前端 vue-tsc 与生产构建通过。
The backend has 74 unit and integration tests with 88% line coverage; ruff reports zero issues;
mypy passes in strict mode across the codebase; the frontend passes vue-tsc and production build.

## 目录结构 / Project Structure

```text
backend/
  app/
    api/            FastAPI 路由与统一错误处理 / Routes and unified error handling
    models/         Pydantic 数据契约 / Data contracts (mirrored by frontend TypeScript)
    services/       高德客户端、候选集、采集编排、缓存、预算、静态图代理 / Amap client, candidates, collection, cache, budget, static-map proxy
    agents/         LLM 客户端与 PlannerAgent / LLM client and PlannerAgent
    config/         配置模块 / Settings
  tests/            pytest 单元/集成测试（mock 外部依赖）/ Unit and integration tests (external deps mocked)
frontend/
  src/
    views/          首页表单与结果页 / Home form and result page
    components/     预算、每日行程、天气、静态图组件 / Budget, day plan, weather, and map components
    services/       axios 封装与本地存储 / Axios wrapper and local storage
    types/          TypeScript 契约与图例色板 / TypeScript contracts and legend palette
    utils/          格式化工具 / Formatting utilities
openspec/           OpenSpec 规划产物（proposal / specs / design / tasks）
```

## 数据契约与安全 / Data Contract & Security

- 金额均为非负整数（元），门票总额由后端精确重算，禁止浮点参与金额运算。
  All amounts are non-negative integers (yuan); totals are recalculated by the backend with no
  floating-point arithmetic.
- 行程中的景点与酒店必须来自高德真实候选，后端强制校验并兜底锚定，杜绝编造。
  Attractions and hotels must come from authentic Amap candidates; the backend enforces and
  reconciles them, eliminating fabrication.
- 天气仅展示服务实际返回的日期，缺失日期明确标注，不补充编造数据。
  Weather displays only service-returned dates; missing dates are explicitly marked.
- 静态图由后端代理，地图密钥不落地前端；不透明 token + 图片缓存 + 单 IP 限流。
  Static maps are proxied by the backend; the map key never reaches the frontend. Opaque tokens,
  image caching, and per-IP rate limiting are applied.
- 外部服务失败必须可感知：明确报错（统一信封）或优雅降级，禁止静默吞异常。
  External failures are always perceptible: explicit errors (unified envelope) or graceful
  degradation — never silently swallowed.

## 当前版本范围与路线图 / Current Scope & Roadmap

**当前版本已包含 / Included in the current release**：行程规划、真实数据采集与缓存、预算计算、
静态地图、天气信息、品牌分享图、多模型适配。
Itinerary planning, real-data collection with caching, budget calculation, static maps, weather,
brand share images, and multi-provider model support.

**未包含 / Not included**：餐饮规划、行程编辑、PDF 导出、交互地图 SDK、图片服务、用户账号与
行程持久化、在线预订支付。后续版本将优先补齐账号体系、行程编辑与预订对接。
Meal planning, itinerary editing, PDF export, interactive-map SDKs, image services, user accounts
with itinerary persistence, and online booking/payment. Future releases will prioritize accounts,
itinerary editing, and booking integration.

## 许可证与声明 / License & Disclaimer

本项目以 MIT 许可证开源，详见 [LICENSE](LICENSE)。
This project is open-sourced under the MIT License — see [LICENSE](LICENSE).

行程、预算与天气信息仅供参考，出行前请以官方最新信息为准。
Itineraries, budgets, and weather are for reference only; always confirm with official sources
before travel.
