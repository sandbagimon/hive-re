# Joint State Sensor Contract

日期：2026-07-16
提交：待提交

## 目标

定义与固定物理时钟同步、可复现且不依赖 viewport refresh 的 joint-state sensor 采样契约。

## 主要改动

- Robotics SensorType 和共享 schema 增加 `joint_state`，保留旧 position/velocity 类型兼容。
- robotics semantic validation 要求 joint-state/position/velocity sensor 提供有效 joint reference。
- `JointStateSensorSample` 定义 stable sensor/joint ID、simulation time、sequence、qpos 和 qvel。
- Scheduler 在 Reset 发布 Home sample sequence 0。
- update_rate 未设置时每 physics step 采样；设置时必须是 physics rate 的整数除数。
- 每个 sensor 维护独立 sequence，Scheduler 只保留 latest sample，避免无界内存增长。
- sample/kinematics 拒绝非有限值、负时间和负 sequence。

## 验证

- 0.01 秒 timestep 下，100Hz 每步采样，50Hz 每两步采样。
- 两个 sensor 的 sequence 分别从 0 递增为 2 和 1，latest payload 顺序稳定。
- 60Hz、101Hz、缺失 joint ID 和 runtime unknown joint 明确拒绝。
- 新 joint_state sensor 通过 schema/model round-trip，null joint 触发 semantic issue。
- Sensor/robotics/schema 聚焦测试：17 passed；Ruff、Mypy 通过。

## 已知限制

- Scheduler 尚未接入 MuJoCo Session/SimulationState。
- 首版仅支持 exact-step divisor，不做 fractional-rate resampling。
- 尚无 noise、latency、frame 或历史 buffer。

## 下一步

接入 MuJoCo fixed step，发布 latest samples，并验证与 recording/RTF 的时间对齐。
