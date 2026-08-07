## Purpose

定义行程规划能力：根据用户输入与真实高德候选数据，由 PlannerAgent 一次生成"整体行程 + 每日行程"双视角的完整旅行计划，是 TripMate 的核心行为契约。

## ADDED Requirements

### Requirement: 生成完整旅行计划
系统 SHALL 接收包含目的地城市、开始/结束日期、旅行天数、偏好、预算档位、交通方式与住宿类型的规划请求，并生成 TripPlan：days 列表（每天 2-3 个景点、酒店、交通、住宿与当日描述）、overall_suggestions、weather_info 与 budget。

#### Scenario: 用户提交完整规划请求
- **WHEN** 用户提交城市=北京、旅行 3 天、偏好=历史文化、预算=中等、交通=公共交通、住宿=经济型酒店的规划请求
- **THEN** 系统返回包含 3 个 DayPlan 的 TripPlan，每天含 2-3 个景点、酒店安排、交通方式与总体建议

### Requirement: 双规划（整体与每日）
规划结果 SHALL 同时满足整体视角（跨天顺序合理、避免地理折返，overall_suggestions 提供全程建议）与每日视角（当日景点就近排序、每天 2-3 个景点）。

#### Scenario: 整体与每日视角一致
- **WHEN** 规划包含 3 天行程
- **THEN** Day N 最后一个景点与 Day N+1 第一个景点地理相近，且每天内部景点按就近顺序排列

### Requirement: 基于真实候选数据规划
景点与酒店 SHALL 来自高德 POI 搜索返回的真实候选数据，系统 MUST NOT 编造景点、酒店或 poi_id。

#### Scenario: 候选数据来源真实
- **WHEN** 规划北京历史文化行程
- **THEN** 行程中的景点与酒店均出自高德返回的候选列表，poi_id 原样引用

### Requirement: 天气数据不编造
天气信息 SHALL 只包含天气服务实际返回的覆盖天数；未覆盖的日期 MUST NOT 出现编造天气。

#### Scenario: 预报未覆盖的天数
- **WHEN** 行程日期超出天气预报覆盖范围
- **THEN** 对应日期无 weather 数据，前端不展示天气且不报错

### Requirement: 规划结果结构校验
系统 SHALL 使用结构化模型校验规划结果；类型、取值范围或必填性不合法时 SHALL 拒绝该结果并触发修复重试（上限 2 次），仍失败则返回明确错误。

#### Scenario: 生成结果不符合契约
- **WHEN** PlannerAgent 返回缺少必填字段或经纬度越界的 JSON
- **THEN** 系统不返回该非法结果，修复重试至多 2 次，仍失败则返回明确错误信息

### Requirement: 外部服务失败可感知
数据采集或 LLM 调用失败时，系统 SHALL 返回可理解的错误信息或降级结果，MUST NOT 静默吞掉异常或以编造数据替代。

#### Scenario: 天气服务不可用
- **WHEN** 天气查询失败且无缓存数据
- **THEN** 系统返回明确的错误提示，不生成包含编造天气的行程

### Requirement: LLM 提供商可配置
系统 SHALL 支持通过配置切换 OpenAI 兼容的 LLM 提供商（如 DeepSeek、Qwen、OpenAI），切换不改变行程规划行为与输出契约。

#### Scenario: 切换 LLM 提供商
- **WHEN** 在 `.env` 中修改 LLM base_url 与 model 为另一 OpenAI 兼容提供商
- **THEN** 系统继续生成符合 TripPlan 契约的行程，无需修改业务代码
