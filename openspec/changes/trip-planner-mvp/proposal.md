## Why

旅行规划存在信息分散、缺少个性化、难以调整三大痛点。TripMate MVP 以"真实数据 + 一次 LLM 生成 + 一键分享"的最小商业闭环切入：用户输入目的地、日期、偏好与预算，系统基于高德真实 POI/天气数据快速生成带地图和预算的完整行程，并可一键生成品牌分享图，行程内嵌预订跳转入口，形成"生成 → 分享 → 跳转"的闭环。

## What Changes

- 从零搭建 TripMate 项目骨架：FastAPI 后端 + Vue3/TypeScript 前端（greenfield，无既有代码迁移）
- 确定性数据采集 + Redis 共享缓存：高德 POI（景点/酒店，48 小时）与天气（4 小时）按"城市 + 规范化查询"共享缓存，成本从"用户数"量级降为"城市 × 偏好"量级；缓存仅作优化层，Redis 不可用时绕过直调
- 单一 PlannerAgent 一次 LLM 调用完成"整体粗排 → 每日细化"双规划，结构化输出 + Pydantic 校验 + 修复重试（≤2 次）
- 静态地图由后端代理生成：服务端持有高德 Key，通过不透明 token 返回同源图片，前端零地图代码；图上含景点全局编号、按天配色、跨天路线连接与酒店标记
- 预算计算收敛为三类（门票/酒店/交通），门票总额由后端基于结构化票价精确重算
- 一键生成品牌分享图（PNG，含地图与天气时间戳），作为传播与获客入口
- 明确裁剪（不纳入 MVP）：餐饮规划、行程编辑、PDF 导出、交互地图 SDK、图片服务（Unsplash）、MCP server
- 密钥统一通过 `.env` 管理，不写入代码仓库

## Capabilities

### New Capabilities
- `itinerary-planning`: 基于用户输入（城市、日期、偏好、预算档、交通、住宿）与真实高德候选数据，由 PlannerAgent 一次生成"整体行程 + 每日行程"双规划的完整旅行计划（景点、酒店、天气、建议、预算），禁止编造数据
- `trip-map`: 由后端生成静态地图图片：景点全局编号、按天配色、跨天路线连接、酒店标记；Key 不落地前端，失败时优雅隐藏
- `budget-calculation`: 按门票、酒店、交通三类计算并展示预算明细；门票总额后端精确重算
- `trip-sharing`: 一键生成含地图与时间戳的品牌分享图（PNG），作为传播入口

### Modified Capabilities
- 无（全新项目，无既有 spec）

## Impact

- 新增目录结构：`backend/`（FastAPI 应用、models、services、agents、api、config）、`frontend/`（Vue3 SPA、views、services、types、router）
- 新增外部依赖：高德 Web 服务 Key（POI 搜索 / 天气 / 静态图）、LLM API Key（OpenAI 兼容端点，默认 DeepSeek）、Redis（本地已安装）
- 新增环境配置：`.env`（含 `.env.example` 模板），密钥不入库
- 影响范围仅限本仓库；无既有系统、API 或数据迁移
