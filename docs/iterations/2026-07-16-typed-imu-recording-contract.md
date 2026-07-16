# Typed IMU Recording Contract

日期：2026-07-16
提交：待提交

## 目标

让 Recording JSON/CSV 表达 typed joint_state/imu emitted events，并保持旧 joint sensor artifact 可迁移。

## 主要改动

- Recording 根级增加 `sensor_types`，stable sensor ID 显式映射 joint_state 或 imu。
- Joint sensor event 增加 `sensor_type=joint_state` 判别字段。
- ImuRecordingState 保存 link ID、time、sequence、orientation xyzw、angular velocity xyz 和 linear acceleration xyz。
- Sample sensors map 改为 typed union，Recorder capture 接受 JointStateSensorSample/ImuSensorSample。
- IMU CSV 每个 stable ID 固定输出 13 列；未 emitted 的 physics row 输出 13 个空字段。
- 旧 payload 缺 sensor_types 或 joint event sensor_type 时自动推断为 joint_state。
- JSON Schema 增加 jointSensorState/imuSensorState oneOf 和 sensor_types。

## 验证

- 两步 IMU recording 仅第二步 emitted，第一行 13 列全空。
- 发射行完整保留 link/time/sequence、xyzw、gyro xyz、acceleration xyz。
- JSON round-trip 与原 artifact 完全一致。
- legacy joint sensor event 去除两个 type 字段后仍恢复为 joint_state。
- sensor IDs/types key mismatch 与未知 type 被拒绝。
- Recording/Schema 聚焦测试 14 passed；Ruff、Mypy（43 source files）、diff check 通过。

## 已知限制

- Session 尚未把 IMU emitted tuple 传给 recorder。
- Recording Panel 仍过滤 IMU checkbox。
- Artifact 暂无 units/covariance/noise metadata。

## 下一步

接入 Session 类型映射和合并 emitted events，再通过真实 Qt 同时导出 joint-state/IMU JSON/CSV。
