# Runtime Fault Containment

日期：2026-07-15
提交：待提交

## 目标

阻止 MuJoCo runtime 异常和非有限数值逃出 Qt event loop，并向用户显示可定位的故障状态。

## 主要改动

- Session 在发布 state 前检查 simulation time、Actor/Link pose、Joint qpos/qvel 和 Actuator ctrl/force。
- 非有限值抛出 `SimulationRuntimeError`，消息包含对象类别、stable ID、字段和 simulation time。
- Runtime fault 同时将 controller 内部状态标记为 fault。
- SimulationService 捕获 frame step 路径中的异常，立即停止 running clock 并清空 accumulator。
- EditorBridge timer callback 捕获异常、停止 QTimer、发布 `simulationStatusChanged("fault")` 并写 Console。
- TypeScript SimulationStatus 和顶部 badge 增加 Fault 状态，继续保留最后一个有效 viewport state。

## 验证

- 注入 NaN joint qpos 后 Session 以具体 joint stable ID 拒绝 state。
- 注入 step exception 后 Service running=false，后续 callback 不再推进。
- Bridge timer 测试证明 QTimer 停止、Fault signal 和 Console message 均只发布一次。
- 完整 Python、TypeScript、ruff、mypy 门禁见提交记录。

## 下一步

让 Reset 返回 Home state 并与 viewport、joint feedback、controller status 原子同步。
