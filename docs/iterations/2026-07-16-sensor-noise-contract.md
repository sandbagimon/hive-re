# Sensor Noise Contract

日期：2026-07-16
提交：待提交

## 目标

定义 local-first、可复现且不会改变默认精确观测的 sensor bias/Gaussian white-noise 配置与随机流规则。

## 主要改动

- Sensor 增加可选 SensorNoise，包含 32-bit seed 与按名称索引的 typed channels。
- Noise channel 同时配置 constant `bias` 与 `standard_deviation`；scalar 使用 number，vector 使用 vec3。
- Joint-state 支持 qpos/qvel；IMU 支持 orientation、angular_velocity、linear_acceleration；contact 支持 normal_force/tangent_force。
- Orientation channel 使用 sensor-frame small-angle rotation vector，单位 rad；runtime 不会直接对 quaternion 分量加噪。
- qpos/qvel 单位跟随 joint（rad 或 m，rad/s 或 m/s）；IMU angular velocity 为 rad/s、acceleration 为 m/s^2；contact force 为 N。
- Schema/semantic validation 拒绝错误 seed、空 channels、跨 sensor type channel、错误维度和负 standard deviation。
- SensorNoiseSampler 以 SHA-256(seed + stable sensor ID + channel) 派生独立 NumPy PCG64 stream。
- 每个 channel 的随机序列彼此独立，Reset 重建 generator；未配置 noise/channel 时精确返回输入。

## 验证

- Robotics model 带 joint qpos/qvel noise 可精确 to_dict/from_dict round-trip。
- Shared Draft 2020-12 schema 与 semantic validator 分别覆盖结构错误和跨类型 channel。
- 同一 sensor reset 后逐值重放 4 个 Gaussian samples。
- 同 stable sensor ID/seed 的 sampler 相同，不同 sensor ID 不同；先采另一个 channel 不影响 qpos stream。
- Zero stddev vector bias 结果精确；None noise 完全保留 scalar/vector 输入。
- Model/noise/schema 聚焦测试 24 passed；Ruff、Mypy 46 source files、TypeScript typecheck 通过。

## 已知限制

- 本提交只建立 contract/sampler，尚未改动 scheduler 发布值。
- 首版只有 constant bias 与 independent Gaussian white noise，不含随机游走、bias drift、量化或带宽模型。
- Seed 是 sensor 配置的一部分，尚未提供 scene/global episode seed override。

## 下一步

把 sampler 接入三类 fixed-step scheduler，并固定 IMU quaternion composition、contact clamp/impulse 规则。
