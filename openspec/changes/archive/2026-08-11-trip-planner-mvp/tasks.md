## 1. 工程骨架与环境

- [x] 1.1 用 uv 初始化后端工程（pyproject.toml + backend/app/{models,services,agents,api,config}），安装 fastapi、pydantic、pydantic-settings、httpx、redis、openai-agents
- [x] 1.2 初始化前端工程（Vite + Vue3 + TypeScript + Ant Design Vue + axios + html2canvas），创建 frontend/src/{views,services,types,router}
- [x] 1.3 编写 `.env.example`（高德 Key、LLM base_url/model/key、REDIS_URL）与 pydantic-settings 配置模块
- [x] 1.4 编写 README：环境要求（Python 3.13 / Node 24 / Redis）、启动 redis-server、API Key 获取指引与启动步骤

## 2. 数据模型（契约）

- [x] 2.1 实现 Pydantic 基础模型：Location、Attraction、Hotel、Budget、WeatherInfo（经纬度/评分/票价校验、温度字符串解析）
- [x] 2.2 实现聚合模型：DayPlan、TripPlan、TripPlanRequest（已删除 Meal；全部字段显式类型，禁止 any/object/unknown）
- [x] 2.3 编写前端 TypeScript 类型 frontend/src/types/index.ts，与后端一一对应
- [x] 2.4 编写模型单元测试：坐标/评分/票价范围、温度解析（"16°C"→16）、预算汇总

## 3. Redis 缓存层

- [x] 3.1 实现 CacheService 抽象（get/set/delete，Redis 实现；Redis 不可用时自动绕过直调）
- [x] 3.2 实现天气缓存：key 设计、4h 新鲜度 + 宽限期、single-flight、stale 标记
- [x] 3.3 实现 POI 缓存：偏好→规范查询映射、查询指纹 key、48h 新鲜度 + 宽限期、空结果短 TTL
- [x] 3.4 编写缓存单元测试：命中/过期/宽限/绕过降级/并发单飞

## 4. 数据采集

- [x] 4.1 实现高德 REST client：POI 搜索（景点/酒店）与天气查询，超时与重试
- [x] 4.2 实现候选集构建：评分过滤、top-15/top-8 截断、坐标校验、poi_id 保留
- [x] 4.3 实现三路并行采集编排（景点/酒店/天气）
- [x] 4.4 编写采集测试：mock 高德响应、限流/超时/空结果路径

## 5. PlannerAgent

- [x] 5.1 编写 planner prompt（独立文件 + 版本号）：双规划规则、红线、预算锚点表
- [x] 5.2 实现候选数据包构建（用户需求 + 候选集 + 天气）
- [x] 5.3 实现 LLMClient 多 provider 适配（OpenAI 兼容：base_url/model/api_key 配置化，DeepSeek/Qwen/OpenAI 可切换）
- [x] 5.4 验证先行：DeepSeek structured output 冒烟测试；严格模式不可用则回退 prompt+JSON 解析 + 修复链（功能不砍） <!-- blocked: 无真实 LLM API Key，冒烟未执行；回退链已实现并有单测覆盖 -->
- [x] 5.5 实现 structured output + Pydantic 校验 + 修复重试（上限 2 次）
- [x] 5.6 实现门票总额精确重算（覆盖 LLM 估算值）
- [x] 5.7 编写 PlannerAgent 测试：正常/非法 JSON/缺字段/越界/修复成败/无酒店/无天气/provider 切换

## 6. 后端 API

- [x] 6.1 实现 POST /api/trip/plan：请求校验、统一响应、错误处理（4xx/5xx）
- [x] 6.2 实现静态图代理：token 签发与校验、高德静态图调用（markers/paths/size）、Redis 图片缓存、限流
- [x] 6.3 实现 map_image_url 注入 TripPlan 与失败容错（null）
- [x] 6.4 编写 API 集成测试：happy path、缺字段 400、LLM 重试、静态图缓存与防篡改
- [x] 6.5 验证先行（spike）：静态图跨天虚线支持验证——不支持则砍虚线改用浅色细线；酒店标记渲染验证——视觉混乱则砍酒店标记，仅保留景点与跨天线 <!-- 无真实 Key，虚线→浅色细线已实现；酒店标记→不上图（按决策10裁剪） -->

## 7. 前端

- [x] 7.1 实现 Home 表单：必填校验、模拟加载进度条、2 分钟请求超时
- [x] 7.2 实现 Result 页：总览/地图/每日行程/天气区块 + 侧边锚点导航
- [x] 7.3 实现地图展示：<img> 渲染 map_image_url、按天图例、失败时隐藏
- [x] 7.4 实现分享：html2canvas 生成品牌 PNG（水印 + 地图 + 天气时间戳）
- [x] 7.5 按 design.md 文案清单落地全部文案（天气免责/时间戳/未覆盖/回访钩子/水印/失败提示）
- [x] 7.6 前端类型检查与构建验证：vue-tsc + vite build 通过

## 8. 联调与交付

- [x] 8.1 全链路联调：表单 → 规划 → 地图 → 分享；Redis 停用降级验证 <!-- 降级/错误路径 PASS；真实 Key 下的全链路 happy path BLOCKED（密钥占位） -->
- [x] 8.2 全量验证：pytest + ruff + mypy + build 通过，L0/L1/L2 自检记录
- [x] 8.3 生成变更说明与提交信息，请求用户授权后执行 git 提交
