# MuJoCo Joint State Sensor Runtime

日期：2026-07-16
提交：待提交

## 目标

将 joint-state sensor 接入 MuJoCo fixed step，并通过 SimulationState 向 Bridge/TypeScript 发布 latest samples。

## 主要改动

- MuJoCo Session 从 RoboticsModel 收集 joint_state sensor definitions。
- `mj_forward` 后发布 Home sample sequence 0，Reset 重置 physics step index 与 sensor sequence。
- 每个 `mj_step` 后按 physics step index capture，再由 recording 读取同一时刻状态。
- SimulationState 增加 sensors 列表并序列化 stable ID、joint ID、time、sequence、qpos/qvel。
- TypeScript SimulationState contract 增加 JointStateSensorSample。
- Scheduler latest sample 不随 QTimer/viewport refresh 重复采样。

## 验证

- 100Hz/50Hz sensors 在 t=0.04 分别为 sequence 4/2。
- Sensor qpos/qvel 与 recording t=0.04 最后一帧一致。
- Recording times 为 0.00 到 0.04 的固定 0.01 秒间隔。
- Reset 后两个 sensor 均回到 sequence 0、time 0。
- Fake clock：0.5x 推进到 t=0.02/seq 1，Pause 10 秒 wall gap 不采样，2x 推进到 t=0.10/seq 5。
- Session/Sensor 聚焦测试：28 passed；TypeScript build、frontend tests、Ruff、Mypy 通过。

## 已知限制

- SimulationState 只发布 latest sample，不含 emitted history。
- Robot Tree/Sensor Inspector 尚未展示 sensors。
- Recording artifact 尚未包含 sensor columns。

## 下一步

增加 Sensor Tree/Inspector，并扩展 recording JSON/CSV 以导出 sensor samples。
