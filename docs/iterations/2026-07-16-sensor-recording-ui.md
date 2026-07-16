# Sensor Recording UI

日期：2026-07-16
提交：待提交

## 目标

让用户从 TypeScript Recording Panel 选择 joint-state sensor，并完成真实 Qt/MuJoCo JSON/CSV 导出闭环。

## 主要改动

- Recording draft 同时维护 selected joint IDs 和 selected sensor IDs，scene sensor 集合变化时安全重建。
- Panel 按 Joints/Sensors 分组显示 checkbox；sensor 默认不选，保持旧 joint-only recording 行为。
- startRecording RPC 配置发送 stable `sensor_ids`，允许 sensor-only recording。
- RecordingSimulationState 增加 `sensor_event_count`，状态区显示 `Rows · Events`。
- Bridge protocol schema 和 TypeScript contract 同步 event count。
- 真实 Qt 测试经 UI 完成选择、录制、停止和 automation path export。

## 验证

- UI 初始存在一个未选 sensor checkbox，点击后 t=0 recording boundary 为 1 row/1 event。
- 50Hz events sequence 从 0 连续递增，相邻 timestamp 固定为 0.02 秒。
- Recording rows 中同时存在 emitted sensor map 和空 map，不重复 latest sample。
- JSON artifact 与 Bridge payload 完全相同；CSV stable sequence 列同时包含空值与连续 sequence。
- 状态文本精确显示 physics rows 与 sensor events。
- 真实 QtWebEngine/MuJoCo E2E 1 passed；截图验证 viewport 非空且关联 link 高亮。

## 已知限制

- 第一版 UI 只支持 joint_state sensor payload。
- Recording event count 汇总所有 selected sensors，尚未提供 per-sensor count。
- 尚无历史曲线、流式写盘或 recording decimation。

## 下一步

建立 link-mounted IMU schema、fixed-step scheduler 和 MuJoCo body-frame runtime mapping。
