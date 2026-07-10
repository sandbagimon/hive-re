# TypeScript Editor Migration

日期：2026-07-10

## 目标

将 SimLab 的编辑器交互迁移到 TypeScript，Python 只保留桌面容器、本地文件、MJCF、validation 和 MuJoCo 服务。

## 已完成

- 新增共享契约：
  - `shared/schemas/scene.schema.json`。
  - `shared/schemas/physics.schema.json`。
  - `shared/schemas/bridge-protocol.schema.json`。
- 建立 TypeScript 构建：`package.json`、`tsconfig.json`、compiled ES modules。
- 将 viewport 和 geometry contract 从 JavaScript 迁移到 TypeScript。
- 新增 TypeScript Editor Store：
  - scene working copy。
  - selection。
  - dirty state。
  - undo/redo history。
  - simulation and validation UI state。
- 将 Asset Browser、Scene Tree、Property Inspector、Console 和全部 toolbar 迁移到 TypeScript。
- 新增 `EditorBridge`，统一提供 Open、Save、Export、Preflight、Run、Pause、Step、Reset RPC。
- MuJoCo state、status 和 console message 通过 QWebChannel events 推送。
- `MainWindow` 缩减为 QWebEngineView + QWebChannel host。
- 删除旧 PySide6 panels、旧 WebViewport bridge 和旧手写 JavaScript。
- 增加 shared schema、EditorBridge、compiled frontend assets 和 EditorStore tests。

## 验证

- `npm run build`：通过。
- `npm run typecheck`：通过。
- `npm run test:frontend`：通过。
- `python -m pytest`：`34 passed`。
- `python -m ruff check .`：通过。

## 已知限制

- 本轮 QtWebEngine GUI screenshot 因沙箱外运行额度限制未能执行。
- 当前 Bridge Protocol 使用 JSON Schema 和 TypeScript types 双重声明，尚未引入自动代码生成。
- TypeScript material preset 数据仍与 Python preset 保持显式镜像，后续应改为共享 JSON 数据源。
