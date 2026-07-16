# Explicit Project Path RPC

日期：2026-07-16
提交：待提交

## 目标

为项目 Save/Open 建立无需原生文件对话框的可测试路径边界。

## 主要改动

- EditorBridge 增加 `openProjectPath(path)`，加载、校验并同步 current path/title/dirty。
- 增加 `saveProjectPath(sceneJson, path)`，校验后创建目录并写入 scene.json。
- 原 `openProject` 和 `saveProject` 对话框路径复用显式 path RPC，避免行为分叉。
- Bridge protocol schema 和 TypeScript PythonBridgeObject 同步新增两个 RPC。
- `window.simlabEditor` automation API 暴露 save/open path，并同步 EditorStore markSaved/loadScene。
- Open path 时清空 trajectory draft cache，确保从文件 clip 重新 hydrate。

## 验证

- Bridge/schema/web asset 聚焦测试：15 passed。
- 覆盖嵌套目录保存、独立 Bridge 重开、path/current state 和非法 scene 不落盘。
- TypeScript build 和 ruff 通过。

## 已知限制

- 显式 path RPC 主要用于自动化和受控集成；普通用户仍通过原生对话框操作。
- 尚未完成带外部 USD 缓存和 trajectory clip 的新窗口重开测试。

## 下一步

完成外部 USD 机械臂 trajectory 的真实 Save/Open/Replay Qt E2E。
