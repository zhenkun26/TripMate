## Context

TripMate_Agent 为全新 greenfield 项目：git 与 OpenSpec 已初始化，Python 3.13 + uv 0.11、Node 24 + npm 11、Redis（redis-server/redis-cli）均已安装。实现参照 hello-agents 第十三章（参考文档已存入 `reference/hello-agents-ch13-intelligent-travel-assistant.md`），动机与能力范围见 proposal.md 与 specs/。方案已按商业化最小闭环精简：确定性数据采集 + 一次 LLM 生成 + 静态图代理 + 分享传播。

## Goals / Non-Goals

**Goals:**
- 前后端分离；前端零地图代码，后端持有高德 Key 并代理静态图
- 真实数据（高德 POI/天气）经 Redis 共享缓存，成本与用户数解耦；缓存仅作优化层，可绕过
- PlannerAgent 一次调用完成双规划，结构化输出 + 校验 + 修复
- 门票预算精确重算，分享图一键生成
- 密钥只存 `.env`；后端 pytest + ruff + mypy，前端 vue-tsc + vite build

**Non-Goals:**
- 餐饮规划、行程编辑、PDF 导出、交互地图 SDK、Unsplash 图片服务、MCP server（均裁剪，v1.x 再议）
- 用户账号与行程持久化（v2）；真实预订支付（仅提供跳转入口）；实时协作、语音、移动端
- 生产级高并发部署（MVP 本地单体运行 + 本地 Redis）

## Decisions

1. **技术栈**：FastAPI + Pydantic v2（后端）；Vue3 + TypeScript + Vite + Ant Design Vue（前端）；uv + npm；OpenAI Agents SDK（仅用其 Runner / structured output）；LLM 默认 DeepSeek（OpenAI 兼容端点，经 `.env` 可切换 Qwen/OpenAI）
2. **数据契约**：`Location` → `Attraction` / `Hotel` / `Budget` / `WeatherInfo` → `DayPlan` → `TripPlan`（已删除 Meal；Budget 为门票/酒店/交通三项）；前端 TS interface 一一对应；整体行程序列由 `days` 拼接派生，不新增 LLM 字段
3. **Redis 缓存层**（`CacheService` 抽象，实现可替换，Redis 不可用自动绕过直调）：
   - 天气：key `tripmate:weather:{adcode}`；新鲜度 4h 由 value 内 `fetched_at` 判定，Redis TTL = 4h + 24h 宽限；懒加载 + single-flight；刷新失败返回旧数据并置 `weather_stale`
   - POI：key `tripmate:poi:v1:{adcode}:{category}:{查询指纹}`；新鲜度 48h，TTL = 48h + 7d 宽限；偏好/住宿类型经规范查询映射保证命中；空结果缓存 30min；景点候选 top-15（评分 ≥4.0）、酒店 top-8
   - 静态图：`tripmate:staticmap:{token}` 存参数（TTL 24h），图片缓存 `tripmate:staticmap:img:{token}`（TTL 24h）
4. **数据采集**：直调高德 REST（POI 搜索 + 天气），不引入 MCP server——确定性采集无需 LLM 自主选工具；景点/酒店/天气三路 asyncio 并行；高德天气 `extensions=all` 返回今日+未来 3 天预报（已核对官方文档，每天约更新 3 次）
5. **PlannerAgent**：一次调用两阶段思考（整体粗排→每日细化）输出 TripPlan；温度 0.3；structured output + Pydantic 校验 + 修复重试 ≤2；prompt 独立文件 + 版本号；预算锚点表辅助估算；门票总额后端精确重算
6. **静态地图代理**：行程生成后把参数写入 Redis token，返回 `map_image_url=/api/trip/static-map/{token}`；代理按 token 取参 → 高德静态图（markers/paths/size 参数已核对官方文档）→ 同源返回 PNG；防篡改（不透明 token）+ 限流；失败 → `map_image_url=null` 前端隐藏
7. **前端**：Home 表单（必填校验 + 模拟进度条 + 2 分钟超时）；Result 页（总览 / 地图 / 每日行程 / 天气，侧边锚点导航）；分享图用 html2canvas（同源图片无跨域污染）+ 品牌水印；图例由前端按"天数→颜色"表渲染
8. **密钥与安全**：`.env` + `.env.example`；高德 Key 仅服务端；静态图代理限流；LLM 超时重试
9. **多 API 适配层**：LLM 走 `LLMClient` 抽象（OpenAI 兼容：`base_url` + `model` + `api_key` 全配置化，DeepSeek/Qwen/OpenAI 可切换，切换不改契约）；高德走 `AmapClient`（POI/天气/静态图三个方法，实现细节收敛在服务层，未来换地图源只改 client）；Redis 走 `CacheService` 抽象。三个适配点都以"改一行配置即可切换、失败路径可感知"为准
10. **验证先行，不好做就砍**：静态图跨天虚线、酒店标记这类"锦上添花"项先在 M2/M3 冒烟验证；若参数不支持、效果混乱或成本高，直接砍掉该项（虚线→浅色细线；酒店标记→不上图），不阻塞主流程

## Risks / Trade-offs

- [LLM 输出不稳定] → structured output + Pydantic 校验 + 修复 ≤2 + 明确报错
- [高德配额/限流] → 天气 4h、POI 48h 共享缓存；空结果短 TTL；静态图按 token 缓存 + 代理限流
- [Redis 依赖] → 可绕过降级直调，缓存不是功能依赖
- [静态图虚线支持未验证] → 验证先行；不支持即砍虚线，用浅色细线区分跨天线
- [酒店标记渲染可能杂乱] → 验证；超过 1 家/晚或视觉混乱即砍掉酒店标记
- [预算估算偏差] → 门票精确重算；酒店/交通按锚点表估算
- [生成耗时] → 单次 LLM + 并行采集，目标 5-15 秒；前端进度条缓解
- [预报覆盖天数有限（今日 + 未来 3 天）] → 不编造、缺失不展示、附带免责文案

## Migration Plan

- greenfield 无迁移；实施顺序：工程骨架 → 数据模型 → Redis 缓存 → 数据采集 → PlannerAgent → API 与静态图代理 → 前端 → 分享 → 联调
- 本地运行：先启动 `redis-server`；后端 `uv run uvicorn app.api.main:app --reload`；前端 `npm run dev`；README 记录 API Key 获取与启动步骤
- 回滚策略：无存量数据，代码回滚即 `git revert`

## 文案清单（落地时原样使用）

- 天气更新时间：`天气数据更新于 {M月D日 HH:mm}`；数据延迟时：`更新于 {M月D日 HH:mm}（数据延迟）`
- 天气免责：`预报通常覆盖未来 3-4 天，仅供参考；天气预报存在不确定性，出行前请以最新预报为准。`
- 预报未覆盖日期：`该日期暂无预报`
- 回访钩子（结果页底部）：`出发前 3 天回来刷新，天气会更准`
- 分享图品牌水印：`TripMate · 智能旅行助手`；分享图入口按钮：`生成我的行程`
- 无酒店兜底：`暂未找到合适的酒店，建议按预算档位自行预订`
- 生成失败：`生成计划失败，请稍后重试`

## Open Questions

- LLM 提供商与模型最终确认（默认 DeepSeek；结构化输出兼容性需冒烟验证）
- 静态图跨天连接线的虚线支持情况（验证任务，失败即砍虚线）
- 酒店上图密度（验证任务，混乱即砍酒店标记）
- "在导航中打开"跳转链接形态（POI 详情页 vs 导航页）——实现时确定
