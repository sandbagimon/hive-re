# Sensor Noise Runtime

日期：2026-07-16
提交：待提交

## 目标

将 deterministic noise sampler 接入 joint-state、IMU、contact fixed-step publish 与 Session Reset/recording 边界。

## 主要改动

- 每个 scheduler binding 持有基于 stable sensor ID 的 SensorNoiseSampler，只在 emitted cadence 调用。
- Reset 先重建 sampler streams，再发布 sequence 0；未发射 physics step 不消耗随机数。
- Joint-state qpos/qvel 应用 scalar constant bias + Gaussian white noise。
- IMU orientation 将 sensor-frame small-angle rotation vector 转 quaternion，右乘 world_from_sensor 并 normalize。
- IMU angular velocity 与 linear acceleration 在 sensor frame 应用 vector additive noise。
- Contact normal force 应用 scalar noise 后 clamp 到非负，normal impulse 从 noisy force × timestep 重算。
- Contact tangent force应用 world-frame vector noise；count、points、normals 保持原始精确值。
- Empty contact 虽消耗 publish sequence 的随机数，但始终发布零 force/impulse/tangent，避免虚假接触。
- Recorder 无需第二次处理，直接保存 scheduler 已发布的 noisy sample。

## 验证

- 50Hz joint-state sensor 在 100Hz physics 中只于 step 2 采样；Reset 后 sequence 0/1 noise 逐值重放。
- IMU 90 度 z small-angle bias 得到单位 `(0,0,sqrt(0.5),sqrt(0.5))` quaternion，vector bias 单位逐项正确。
- Empty contact 保持全零；active 12N + 2N bias 得到 14N/0.14N·s，tangent bias 与 points/normals 保持正确。
- -20N bias 后 normal force/impulse clamp 为 0。
- MuJoCo Session t=0 与 step2 noisy sample、Reset replay 和 recording typed event 完全一致。
- Scheduler/noise 聚焦测试 22 passed；Ruff、Mypy 46 source files 通过。

## 已知限制

- Noise 配置尚未在 Sensor Inspector 中显示或编辑。
- Contact force clamp 会使接近零处的 Gaussian 分布成为截断分布，这是非负力约束的预期结果。
- 仍无 episode/global seed override；Reset 固定重放 authored sensor seed。

## 下一步

在 Sensor Inspector 显示 seed/channel/bias/stddev/unit，并做 Qt runtime/recording/Reset E2E。
