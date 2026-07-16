# Sensor Recording Contract

日期：2026-07-16
提交：待提交

## 目标

让 fixed-step recording artifact 表达 joint-state sensor 的真实 emitted cadence，并保持稳定、可迁移的 JSON/CSV 格式。

## 主要改动

- JointStateRecording 增加 selected `sensor_ids`，每个 physics sample 增加 emitted-only `sensors` map。
- SensorRecordingState 保存 joint ID、sensor timestamp、sequence、qpos 和 qvel。
- Recorder `capture` 接收当前 physics step 的 emitted sensor tuple，只保留被选择的 stable sensor IDs。
- CSV 每个 sensor 固定输出 joint_id/time/sequence/qpos/qvel 五列；未 emitted 的行写空字段。
- `from_dict` 对旧的不含 sensor_ids/sample.sensors 的 1.0 artifact 使用空集合迁移。
- JSON Schema 增加 sensor state、sensor IDs 和 sample sensors 定义。

## 验证

- 两个 physics step 中仅第二步 emitted，JSON 第一帧 sensors 为空、第二帧 sequence 为 1。
- CSV sensor header 使用 stable sensor ID，空步五列为空，发射步完整保留 event。
- 去除 sensor 字段后的 legacy payload 仍可加载。
- 重复 sensor ID 被 recorder 拒绝。
- Recording/Schema 聚焦测试 11 passed；Ruff、Mypy、diff check 通过。

## 已知限制

- MuJoCo Session 尚未把 Scheduler emitted tuple 传入 recorder。
- Bridge/UI 尚未提供 sensor selection。
- 第一版 payload 只定义 joint_state sensor 字段。

## 下一步

接入 Session/Service/Bridge，并验证 100Hz/50Hz runtime cadence 和导出内容。
