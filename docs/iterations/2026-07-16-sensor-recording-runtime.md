# Sensor Recording Runtime

日期：2026-07-16
提交：待提交

## 目标

将 joint-state sensor emitted events 从 MuJoCo fixed step 贯通到 Recording Service、Bridge 和 JSON/CSV export。

## 主要改动

- Session 保存可记录的 stable sensor ID 集合，start 时拒绝未知选择。
- 每个 `mj_step` 保留 Scheduler.capture 返回的 emitted tuple，并与同一时刻 physics state 一起交给 recorder。
- t=0 recording boundary 包含 Scheduler reset 生成的 Home sequence 0；非零时间启动不复制 stale latest sample。
- SimulationService 和 EditorBridge 的 startRecording 配置增加可选 `sensor_ids`。
- Bridge 的 JSON/CSV 导出沿用 Recording Contract 的 stable sensor columns。

## 验证

- 100Hz/50Hz sensors 在五个 recording rows 中分别按每步/每两步出现。
- 50Hz sequence 为 0、1、2；未 emitted 的行 sensors map 为空。
- Bridge fake clock 生成 7 rows，50Hz sensor sequence 为 0 到 3，CSV 含 stable sequence column。
- 未知 sensor ID 在 recording 启动前返回明确错误。
- Session/Bridge/Recording 聚焦测试 12 passed；Ruff、Mypy、diff check 通过。

## 已知限制

- Recording Panel 尚未提供 sensor checkbox。
- Runtime 状态仅报告 physics row sample_count，尚未单独显示 sensor event count。
- 第一版只记录 joint_state sensor。

## 下一步

补 TypeScript Recording Panel sensor 选择、event count 和真实 Qt JSON/CSV 导出验收。
