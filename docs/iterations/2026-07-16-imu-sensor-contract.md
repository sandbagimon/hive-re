# IMU Sensor Contract

日期：2026-07-16
提交：待提交

## 目标

建立 link-mounted IMU 的共享 schema/model、坐标约定和 fixed-step sampling contract。

## 主要改动

- Robotics Sensor 增加可选 `local_transform`，表示 sensor frame 在 link frame 中的位姿，四元数为 xyzw。
- IMU 语义校验要求合法 link、local transform 和 normalized local quaternion。
- 非 IMU/旧 sensor 不序列化缺省 local_transform，保持现有 scene round-trip 完全一致。
- ImuKinematics 定义 `world_from_sensor` orientation，以及 sensor-frame angular velocity 和 proper linear acceleration。
- ImuSensorSample 包含 stable sensor/link IDs、simulation timestamp、sequence 和三个 IMU payload。
- ImuSensorScheduler 按 physics rate 的 exact integer divisor 调度，并维护 deterministic latest/reset sequence。
- TypeScript RobotSensor contract 同步 local transform。

## 验证

- IMU schema/model round-trip 保留 link/local pose；缺 link/pose、dangling link 和非法 quaternion 均有明确 code。
- 100Hz/50Hz 在 0.01 秒 timestep 下按每步/每两步发射，Reset sequence 从 0 开始。
- Payload 序列化为 world_from_sensor xyzw、sensor-frame velocity/acceleration。
- 非 divisor 60/101Hz、缺 measurement 和非 normalized orientation 被拒绝。
- IMU/Robotics/Schema 聚焦测试 20 passed；Ruff、Mypy（43 source files）、TypeScript build 通过。

## 已知限制

- MuJoCo exporter 尚未生成 IMU site/sensor elements。
- SimulationState、Recording 和 Inspector 尚未接收 IMU samples。
- 暂无 noise、bias、drift、covariance 或 calibration 模型。

## 下一步

将 IMU local pose 转换为 MJCF site/sensors，并从 sensordata 构建 fixed-step runtime samples。
