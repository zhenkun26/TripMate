# TripMate 前端（tripmate-frontend）

基于 Vue 3 + TypeScript + Vite + Ant Design Vue 的旅行规划单页应用，提供行程表单、
结果展示、静态地图与品牌分享图功能。项目整体说明见仓库根目录 [README](../README.md)。

## 本地开发

```bash
npm install
npm run dev
```

开发服务器默认运行于 http://localhost:5173 ，`/api` 请求由 Vite 代理转发至
`http://localhost:8000`（后端）。

## 构建与检查

```bash
npm run build    # vue-tsc 类型检查 + vite 生产构建
```

## 目录结构

```text
src/
  views/        Home 表单 / Result 结果页
  components/   预算、每日行程、天气、静态图与图例组件
  services/     axios 封装（统一响应信封、2 分钟超时）与本地存储
  types/        TypeScript 数据契约（与后端 Pydantic 模型一一对应）
  utils/        日期格式化工具
  router/       路由配置
```

## 注意事项

- 前后端契约同步：修改 [types/index.ts](src/types/index.ts) 时必须同步后端
  `backend/app/models/schemas.py`。
- 静态图由后端代理生成（不透明 token），前端仅以 `<img>` 展示，不接触高德 Key。
