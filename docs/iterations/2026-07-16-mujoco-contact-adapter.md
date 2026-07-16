# MuJoCo Contact Aggregation Adapter

日期：2026-07-16
提交：待提交

## 目标

把 MuJoCo 原生 contacts/wrenches 转换为 ContactMeasurement 的 stable scope、world-frame 有界聚合。

## 主要改动

- 添加 NumPy 显式运行依赖，用于 MuJoCo `mj_contactForce` 要求的 writable float64 buffer。
- Adapter 从 RoboticsModel 建立 collider stable ID 或 link collider 集合到 MuJoCo geom IDs 的严格映射。
- 同时位于 scope 内的 contact 被过滤，只聚合 scope 与外部 geometry 的接触。
- Contact-frame tangent force 转换为 world frame，并调整为作用于 scoped geometry 的方向。
- World normal 统一为 scoped geometry 指向对方；contact point 使用 MuJoCo world position。
- Normal force/tangent force 求和，normal impulse 为 normal force 乘 fixed timestep。
- 所有 contact 计数保留，按 normal force 降序最多输出 8 个 points/normals。
- Exporter 公开 deterministic stable ID -> MuJoCo XML name helper，避免 adapter 重复命名规则。

## 验证

- Collider scope 与 link scope 均从 no-contact 聚合为空，再在 box 落到可见 Ground 后检测 contact。
- 1kg 静止 box normal force 约 9.81N，0.01 秒 impulse 约 0.0981N·s。
- Scoped box 指向 Ground 的 world normal 为 `(0,0,-1)`，contact point z 约 0。
- 水平滑动时 world tangent force x 为负，确认摩擦作用方向与 scoped velocity 相反。
- Missing stable collider/geom mapping 返回包含 collider ID 的明确错误。
- Adapter/Contract 聚焦测试 9 passed；Ruff、Mypy（45 source files）、diff check 通过。

## 已知限制

- Contact adapter 尚未接入 Session/Scheduler/SimulationState。
- Impulse 为该 publish step 的 `normal_force * timestep`，不是跨降采样周期积分。
- 未输出 torque、per-contact geom pair 或 friction cone diagnostics。

## 下一步

接入 Session fixed-step runtime 与 typed Sensor Inspector，并验证机器人/可见 Ground 接触状态转换。
