# Controller Safety

日期：2026-07-15
提交：待提交

## 目标

让机械臂控制命令具备原子更新、可观测 fault 和可配置 watchdog，避免错误输入留下不可见的部分状态。

## 主要改动

- joint target 先完成 stable ID、数值有限性和 range 验证，再一次性写入 actuator ctrl。
- 任一 target 无效时整批失败，旧 ctrl 全部保留，controller 状态进入 `fault`。
- SimulationState 和共享 Bridge Schema 增加 controller status、message、command time、timeout。
- `simulation_config.control_timeout` 接受非负秒数；正数按 MuJoCo simulation time 启用 watchdog。
- watchdog 超时后将 position targets 恢复 Home，并发布 `timed_out` 和可读消息。
- Bridge 的失败响应带回当前 runtime state，Joint Control UI 显示 ready/active/timed out/fault。
- timeout 默认关闭，保持当前 position setpoint 的一次设置、持续保持语义。

## 验证

- 原子失败测试证明有效 shoulder 与无效 joint 混合提交不会改变任何 ctrl。
- watchdog 测试证明超时后两个 actuator 均恢复导入的 Home target。
- Bridge 测试证明 RPC 错误响应包含 controller fault state。
- 完整 Python、TypeScript、ruff、mypy 门禁见提交记录。

## 下一步

增加持续交替 target 的机械臂 soak test 和有限状态诊断。
