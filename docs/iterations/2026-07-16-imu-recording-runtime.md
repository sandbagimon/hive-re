# IMU Recording Runtime

日期：2026-07-16
提交：待提交

## 目标

让 Session/UI 同时选择、记录并导出 joint-state 与 IMU fixed-step events。

## 主要改动

- Session 建立 stable sensor ID 到 joint_state/imu type map，startRecording 传入精确类型。
- 每个 physics step 合并两个 Scheduler 的 emitted tuple 后一次 capture，保持共同 row timestamp。
- t=0 recording boundary 同时包含所有 selected sensor 的 sequence 0 sample。
- Recording Panel 不再过滤 IMU，scene sensor 变化会重建包含两类 checkbox 的 draft。
- Runtime `sensor_event_count` 汇总所有 selected typed events。
- Qt workflow 同时选择两类 sensor，并经 automation path export JSON/CSV。

## 验证

- Session IMU-only recording 三行中事件分布为 emitted/empty/emitted，event count 为 1/2。
- Recording sensor_types 精确保存 IMU 类型，sample payload discriminator 为 imu。
- 真实 Qt 同时选择 joint-state/IMU，t=0 active 状态为 1 row/2 events。
- 两类 50Hz sequence 都从 0 连续递增，相邻 event timestamp 为 0.02 秒。
- JSON sensor_types 与 typed samples 正确；CSV 同时包含 joint sequence、IMU orientation.w 和 acceleration.z。
- CSV 两种 sequence 列均与各自 event history 一致，physics 空步保持空值。
- QtWebEngine/MuJoCo E2E 1 passed；Runtime/Recording 聚焦测试 16 passed。

## 已知限制

- Recording UI 只显示总 event count，不显示 per-sensor count。
- JSON/CSV 尚无 units、covariance、noise 或 calibration metadata。
- 长时间 recording 仍为内存缓冲，不支持 streaming writer。

## 下一步

建立 Contact Sensor Contract 和 MuJoCo contact aggregation adapter。
