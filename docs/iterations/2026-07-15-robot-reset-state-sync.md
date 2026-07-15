# Robot Reset State Sync

日期：2026-07-15
提交：待提交

## 目标

让 Reset 明确恢复外部机械臂 Home state，并保证 viewport、joint feedback 和 controller 状态同步。

## 主要改动

- SimulationService `reset()` 返回 Home SimulationState，并保留已编译 MuJoCo session。
- Reset 停止 fixed clock、清空 accumulator，但不卸载 model；下一次 Run 无需重新导出和编译。
- 新增 `stop()`，专门用于 Scene 变化、打开项目、shutdown 等 model 已失效的场景。
- EditorBridge Reset 发布 Home state 和 Paused status；无已加载 session 时保持 Stopped。
- TypeScript Reset 使用 RPC 返回 state，不再无条件清空 simulationState。
- Home state 包含 time=0、导入初始 qpos/ctrl 和 controller ready。

## 验证

- Service 测试证明 Reset 前后 session identity 不变，Stop 才释放 session。
- Bridge 测试证明 Home state response 与 signal 内容一致，status 为 Paused。
- 完整 Python、TypeScript、ruff、mypy 门禁见提交记录。

## 下一步

增加可测试的 path-based OpenUSD RPC，覆盖完整 Bridge robot workflow。
