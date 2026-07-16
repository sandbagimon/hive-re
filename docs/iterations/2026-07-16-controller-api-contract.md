# Per-Step Controller API Contract

日期：2026-07-16
提交：待提交

## 目标

为用户 Python 控制逻辑建立不暴露可变 MuJoCo 内部状态的稳定 per-step 边界。

## 主要改动

- `ControllerObservation` 提供 time、timestep、joint qpos/qvel 和 actuator ctrl/force。
- observation 内部映射和叶节点均不可变，稳定 ID 是唯一索引。
- `ControllerAction` 第一版只表达 joint position target map，并拒绝空 ID 与非有限值。
- `StepController` Protocol 定义 `reset(observation)` 和 `step(observation)`。
- `ControllerRunner` 管理 attach/detach、ready/active/fault、step count 和执行耗时。
- controller reset/step 异常被隔离为 fault，故障后不再调用用户代码。
- 可选 deadline 超时会丢弃本步 action 并停用 controller。

## 验证

- observation/action 不可变性、正常生命周期、异常隔离和 deadline：6 passed。
- Ruff 通过。
- Mypy：38 source files 无问题。

## 已知限制

- Contract 尚未接入 MuJoCo Session。
- 第一版 action 只有 position targets，没有 velocity 或 torque command。
- 尚未提供从项目文件加载用户 controller module 的入口。

## 下一步

将 ControllerRunner 接入每个 MuJoCo step，并用外部 OpenUSD 双关节机械臂验证闭环。
