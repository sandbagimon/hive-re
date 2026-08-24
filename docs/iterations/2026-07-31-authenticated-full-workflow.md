# Authenticated Full Workflow and Development Token Fix

日期：2026-07-31  
提交：待提交

## 目标

使用实际启动脚本和浏览器/API 链路运行一次完整 BeeFoundrySim 工作流，主动查找现有自动化没有覆盖的
集成故障；修复后重复原路径，并执行全量回归。

## 完整工作流

- 使用 Playwright 启动独立 Vite 前端和 FastAPI 后端。
- 创建浏览器 Project，加载共享 Asset Catalog 和 Franka Panda 二进制 Geometry Bundle。
- 添加、选择和移动 Actor，确认编辑后选择状态保留且缓存几何不重复加载。
- 导入单文件 OpenUSD 机器人和带相对依赖的 OpenUSD Folder。
- 创建 Simulation，执行 Preflight、Run、Pause、Step、Stop，并验证编辑状态和运行状态隔离。
- 加载/重载可信 Python Controller，播放 Trajectory，开始/停止 Recording 并导出 JSON。
- 验证双浏览器 Project/Simulation 隔离和 WebSocket sequence 断线续传。
- 使用 `start_backend.sh` 同时启动 REST API 与 gRPC 数据面，并通过 `start_frontend.sh` 启动
  Vite 代理。
- 通过真实 API 创建 Franka Scene，执行 MuJoCo Preflight，加载
  `franka_joint1_wave.py`，运行到 0.304 秒、完成 152 次 Controller step 后 Stop。

## 发现的 Bug

当后端通过 `BEEFOUNDRYSIM_API_TOKEN` 开启 Bearer 鉴权时，Vite development runtime config 仍把
`accessToken` 固定为 `null`。浏览器可以访问未鉴权的 `/health`，但随后创建 Project 返回
401，因此用户看到的是“页面能打开但资产为空/BeeFoundrySim API unavailable”。

该问题没有被原 Web E2E 捕获，因为测试用 `page.route()` 注入了自定义 token config，绕过了
Vite 自己生成 `/beefoundrysim-config.json` 的路径。

## 根因

- `frontend/vite.config.mjs` 的 development middleware 硬编码 `accessToken: null`。
- `start_frontend.sh` 只传递 API proxy target，没有把开发环境的 API token交给 Vite。
- 后端启动脚本与前端启动脚本之间缺少同一鉴权配置的显式约定。

## 修复

- Vite development config 优先读取 `BEEFOUNDRYSIM_FRONTEND_ACCESS_TOKEN`，其次读取
  `BEEFOUNDRYSIM_API_TOKEN`，没有值时保持 `null`。
- `start_frontend.sh` 在未显式设置前端 token 时，从 `BEEFOUNDRYSIM_API_TOKEN` 安全继承到 Vite
  进程；脚本不打印 token。
- 增加 Node 回归测试，直接调用 Vite middleware 并验证 no-store runtime config 中的 token。
- README 补充两个终端的鉴权启动方式，并明确这种共享 token 只适用于可信开发环境；生产环境
  不应把共享秘密写入静态 bundle。

## 验证

- 修复前复现：设置 `BEEFOUNDRYSIM_API_TOKEN=workflow-secret` 后，runtime config 仍返回
  `accessToken: null`。
- 修复后真实启动：runtime token 注入成功；无 Token 创建 Project 返回 401；带 Token 创建
  Project 返回 201；随后读取 12 个共享资产并确认 Franka 可用。
- Playwright 完整 Web workflow：12 passed。
- gRPC 本地/远程相同 Gym Environment 与 token 拒绝测试：2 passed。
- Python 全量：234 passed、3 skipped。
- 前端 Store、Simulation、Trajectory、Robot Kinematics、Geometry Bundle 和 Vite Runtime
  Config 测试全部通过。
- TypeScript/Vite production build、Ruff、Mypy 和 shell syntax check 通过。

## 已知限制

- 开发 token 会返回给能够访问 Vite development server 的浏览器，只能用于可信开发网络。
- production preview 使用部署提供的静态 `beefoundrysim-config.json`，本次修复不会自动向静态构建
  注入 secret。
- 当前 E2E 仍通过 route override 测试跨域 token；后续应增加一个直接启动 Vite dev middleware
  的独立浏览器鉴权用例。

## 下一步

- 为生产部署接入用户级短期 token 或反向代理身份头，避免共享长期 secret。
- 为 `start_backend.sh`/`start_frontend.sh` 增加自动化 launcher smoke test。
- 将真实 Franka Controller workflow 固化为独立 E2E，检查关节目标变化和 Stop 后资源释放。
