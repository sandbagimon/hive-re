# Complete Web Frontend and Backend Decoupling

日期：2026-07-28

## 目标

将 TypeScript/three.js 编辑器变成独立静态产品，将 Python 变成只提供版本化资源 API 的后端；两者能够独立构建、部署、升级和测试，Qt 只作为 HTTP(S) Web 客户端。

## 完成内容

- 前端源码物理迁至 `frontend/src`，Vite 独立输出 `frontend/dist`；Python wheel 不再包含 HTML、TypeScript、CSS、three.js 或编译后 JS。
- `simlab-config.json` 在运行时选择 HTTP API、WebSocket、API 版本、可选 project ID 与 token，前端不要求同源。
- FastAPI 只暴露 `/api/v1`、OpenAPI 和 API docs，不托管页面，不暴露通用方法 RPC，也不暴露服务器文件路径。
- `project`、`simulation`、`artifact` 采用不透明 ID；Scene、OpenUSD、controller 使用内容上传，MJCF/recording 使用 artifact 下载。
- 每个 simulation 持有独立 application/MuJoCo session；两个浏览器客户端的 project、simulation 和 runtime state 完全隔离。
- WebSocket 绑定 simulation ID，事件含单调 sequence；短断线使用 `after_sequence` 增量补发，游标过旧时回退 snapshot，浏览器指数退避重连。
- CORS 为显式 allow-list；HTTP Bearer 与 WebSocket token 共用可选鉴权；Python controller 默认禁止执行，仅可信后端显式开关启用。
- Qt MainWindow 只加载 `SIMLAB_FRONTEND_URL`/`--frontend-url`，没有 QWebChannel、project root、模拟 service 或本地前端文件。
- 保留 transport-neutral `WebApplication` 作为后端内部应用服务，旧 `EditorBridge` 只作为未接入产品入口的兼容模块，公共 Web 契约不依赖它。

## 验证

- Python v1 契约：后端根路径与旧 RPC 返回 404，project/simulation/artifact CRUD、下载、token、CORS、controller deny-by-default 和双 simulation 隔离通过。
- Vite production build：source map 确认入口为 `frontend/src/ts/app.ts` 与新 API bridge，不包含旧 generated/QWebChannel bridge。
- Playwright 使用 4173 静态前端跨域连接 8876 API：
  - 整套后端强制 token；缺失 HTTP token 返回 401，缺失 WebSocket token 返回 4401；
  - Scene Open、Run/Pause、实时 RTF、Save JSON、MJCF artifact 下载；
  - 外部 OpenUSD 机器人、trajectory、可信 controller、recording artifact；
  - 两个页面得到不同 project/simulation ID，运行状态互不影响；
  - WebSocket 从 sequence 4 断开，离线产生事件后按 cursor 重连，收到增量事件而不是 snapshot。
- TypeScript typecheck、前端 store/trajectory 单测、Ruff、Mypy 与全量 Python 回归作为最终发布门禁执行。

## 安全边界

远程生产仍需由部署层提供 TLS、真实身份签发的短期/用户级 token、速率与请求体配额。`--allow-controller-execution` 只适用于可信专用后端，不构成不可信 Python 沙箱。上述属于部署加固责任，不再是前后端代码或发布耦合。
