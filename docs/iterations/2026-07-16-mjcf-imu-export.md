# MJCF IMU Export

日期：2026-07-16
提交：待提交

## 目标

把 link-mounted IMU definition 转换为可由 MuJoCo 编译的 site 和原生 sensor channels。

## 主要改动

- Articulation export 按 link ID 收集 IMU，并在对应 nested body 下创建 site。
- Site pos 使用 local_transform position，xyzw quaternion 转为 MJCF wxyz。
- 每个 IMU 输出 framequat、gyro 和 accelerometer，通道名由 stable sensor ID 确定派生。
- Site 使用固定 5mm debug marker 属性，不参与碰撞。
- 缺 local transform 时 exporter 返回带 sensor ID 的明确错误。

## 验证

- 带 `sensor.forearm:imu` stable ID 的 fixture 输出安全 XML 名 `sensor_forearm_imu_*`。
- Site 位于 forearm body，pos 为 0/0/0.2，quat 为 1/0/0/0。
- framequat 正确引用 site，gyro/accelerometer 使用同一 site。
- MuJoCo 真编译得到 3 sensors，dimensions 为 4、3、3。
- MJCF exporter 测试 10 passed；Ruff、Mypy（43 source files）、diff check 通过。

## 已知限制

- Session 尚未读取 sensordata。
- Site 仅用于计算/轻量调试，viewport 尚未显示 sensor frame。
- 未实现 noise、bias 或 calibration。

## 下一步

建立 stable sensor channel address mapping，并发布 fixed-step ImuSensorSample 到 SimulationState。
