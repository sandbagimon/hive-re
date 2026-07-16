# MuJoCo IMU Runtime

日期：2026-07-16
提交：待提交

## 目标

从 MuJoCo 原生 IMU channels 发布 fixed-step ImuSensorSample，并扩展 Bridge/TypeScript runtime union。

## 主要改动

- Exporter 与 Session 共享 stable sensor ID 到三个 MJCF channel names 的确定映射。
- Session 编译后解析 channel sensor ID、address 和 dimension，严格要求 framequat/gyro/accelerometer 为 4/3/3。
- sensordata framequat 从 MuJoCo wxyz 转为 SimLab xyzw；gyro 和 accelerometer 保留 sensor-frame 原值。
- ImuSensorScheduler 与 joint-state scheduler 在同一 physics step index 上 capture/reset。
- SimulationState sensors 支持带 `sensor_type` 判别字段的 joint_state/imu union。
- Bridge protocol schema 和 TypeScript contract 定义 typed IMU payload。
- Sensor Inspector 根据类型显示 Joint 或 Link，并实时更新 IMU orientation/angular velocity/linear acceleration。
- Recording Panel 目前只列 joint_state，避免 IMU 被选择后静默导出空事件。

## 验证

- Fixed base IMU Home orientation 为 identity、gyro/accelerometer 为 MuJoCo 的零输出，100Hz 每步递增。
- Forearm 50Hz IMU 在受控关节运动后 sequence 1/time 0.02，local angular velocity 明显非零。
- Runtime orientation 保持 normalized，serialization 含 `sensor_type=imu`。
- Reset 后两个 IMU 均回到 sequence 0/time 0。
- 尝试作为旧 joint-state recording sensor 选择 IMU 会明确报 unknown/unsupported ID。
- Runtime/Schema 聚焦测试 6 passed；Ruff、Mypy（43 source files）、TypeScript build/frontend tests 通过。

## 已知限制

- Qt IMU Inspector 尚无真实端到端截图测试。
- Recording artifact 尚未定义 IMU vector columns。
- MuJoCo 对 world-welded fixed body accelerometer 输出为零；SimLab 不人为注入重力值。
- 尚无 noise、bias、drift 或 calibration。

## 下一步

增加真实 Qt IMU Inspector E2E，再将 typed IMU events 纳入 Recording JSON/CSV。
