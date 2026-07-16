# Contact Recording Contract

日期：2026-07-16
提交：待提交

## 目标

为 contact sensor 定义可 round-trip、可 schema 校验且列顺序稳定的 typed recording JSON/CSV contract。

## 主要改动

- RecordingSensorType 与 TypedSensorRecordingState 增加 `contact` / ContactRecordingState。
- JSON event 保存 time、sequence、完整 contact_count、normal force/impulse、world tangent force 和有界 points/normals。
- JointStateRecorder 接受 ContactSensorSample，并对全部 contact scalar/vector 值执行 finite 检查。
- Shared recording schema 增加 contactSensorState，points/normals 分别限制最多 8 个 vec3。
- 每个 contact sensor 固定分配 56 个 CSV columns：8 个聚合字段与 8 组 point xyz/normal xyz。
- 未发射 event 的整组列为空；不足 8 个 retained points 时，剩余 slot 为空。

## 验证

- Contact event 从 recorder capture 到 model `to_dict()/from_dict()` 精确 round-trip。
- 生成 payload 通过 Draft 2020-12 shared JSON Schema validation。
- CSV header 固定为 56 个 sensor columns，slot 0-7 顺序与空 cell 行为逐项断言。
- Contact recording/shared schema 聚焦测试 15 passed；Mypy 45 source files 通过。

## 已知限制

- Session 仍暂时拒绝选择 contact sensor recording；本提交只固定数据契约。
- CSV 不重复存储 collider/link scope，scope 由 scene robotics schema 中相同 stable sensor ID 解析。
- Per-contact force 未记录；每个 event 保存聚合 wrench 与有界几何接触集合。

## 下一步

将 contact emitted cadence 接入 Session recorder 和 Recording Panel，再做运行时 JSON/CSV 验收。
