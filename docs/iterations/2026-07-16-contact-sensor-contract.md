# Contact Sensor Contract

日期：2026-07-16
提交：待提交

## 目标

建立有界、确定的 contact sensor schema/model、聚合 payload 和 fixed-step scheduler。

## 主要改动

- Robotics Sensor 增加可选 collider_id 和 aggregation_mode。
- Contact sensor 必须在 link_id/collider_id 中二选一；首版 aggregation_mode 固定为 sum。
- Validation 检查 dangling collider、scope 冲突和缺失 aggregation。
- ContactMeasurement 定义 contact_count、normal_force、normal_impulse、world tangent_force 和 world points/normals。
- Points/normals 长度必须相等，最多 8 个；normals 必须 normalized。
- Empty measurement 强制 zero force/impulse 且无 points，避免自相矛盾状态。
- ContactSensorScheduler 按 physics exact divisor 发布 stable sequence/latest/reset samples。
- TypeScript RobotSensor contract 同步 collider scope 与 aggregation。

## 验证

- Collider-scoped contact sensor schema/model round-trip 完全一致。
- 同时设置 link/collider、缺 aggregation 和 dangling collider 均产生明确 validation code。
- 100Hz/50Hz scheduler 在 0.01 秒 timestep 下按每步/每两步发射。
- Active sample 序列化 count、force、impulse 和 world point/normal；Reset 从 empty sequence 0 开始。
- 不等长 points/normals、超过 8 点、非 normalized normal、非零 empty payload 被拒绝。
- Contact/Robotics/Schema 聚焦测试 22 passed；Ruff、Mypy（44 source files）、TypeScript build 通过。

## 已知限制

- MuJoCo contact aggregation adapter 尚未实现。
- SimulationState、Recording 和 Inspector 尚不支持 contact sample。
- 首版只支持 sum，不支持 max/per-pair/history aggregation。

## 下一步

映射 stable collider/link scope 到 MuJoCo geom IDs，并把 contact-frame wrench 转换为有界 world-frame aggregate。
