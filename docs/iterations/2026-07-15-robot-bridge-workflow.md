# Robot Bridge Workflow

日期：2026-07-15
提交：待提交

## 目标

消除原生 QFileDialog 对自动化验收的阻塞，证明真实 UI RPC 边界可以完整操作外部 USD 机械臂。

## 主要改动

- 新增 `importOpenUsdPath(path)` QWebChannel RPC，返回与 `importOpenUsd()` 相同的 asset/robotics payload。
- 原有 Import USD 文件对话框只负责选路径，导入、warning 和 Console 行为复用 path RPC。
- TypeScript Bridge interface 和共享协议 schema 声明新方法。
- Bridge workflow 使用可控墙钟驱动真实 fixed-clock callback，不直接调用 Session step。
- 验收从外部绝对路径开始，覆盖 robot actor、Run、joint targets、0.8 simulation seconds、Pause、Reset。
- 验证 shoulder 实际运动、controller active、状态 signal 顺序以及 Reset Home qpos。

## 验证

- Bridge 和 schema 聚焦测试：10 passed。
- 完整 Python、TypeScript、ruff、mypy 门禁见提交记录。

## 下一步

增加适合机械臂调试的 joint Jog 控制和 step size。
