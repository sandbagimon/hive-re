# Physics-Step Recording Runtime and RPC

日期：2026-07-16
提交：待提交

## 目标

让机械臂状态记录按真实 MuJoCo physics step 采样，并通过 Bridge 可控、可导出。

## 主要改动

- MuJoCoSimulationSession 持有 bounded JointStateRecorder。
- Start 默认选择 Session 全部 joints/actuators，也支持 stable ID 子集。
- Start capture 当前初始 state；之后每个 `mj_step` 后 capture 一次。
- 一个 fixed-clock callback 补算多个 step 时生成相同数量 samples，不按 UI frame 降采样。
- SimulationState 增加 recording active/sample_count/limit_reached/name。
- `simulation_config.recording_max_samples` 控制硬上限，默认 100,000。
- Reset 自动停止活动 recording，避免 simulation time 回退破坏严格时间序列。
- SimulationService 提供 start/stop/get 和 JSON/CSV path export。
- EditorBridge 增加 startRecording、stopRecording、getRecording、exportRecording RPC。
- Bridge protocol 和 TypeScript runtime state/method types 同步更新。

## 验证

- Session/Bridge/recording/schema 聚焦测试：31 passed。
- 4 个 `mj_step` 产生初始 sample 加 4 个 step samples，times 为 0.00-0.04。
- max_samples=3 时停止在 3，不继续增长。
- Bridge fixed clock 产生 7 samples，并导出可解析 JSON 和 8 行 CSV（含 header）。
- ruff 和 mypy 通过。

## 已知限制

- UI 尚未提供 recording controls 和 sample count。
- Export RPC 使用显式 path，普通 UI 尚未接原生 Save dialog。

## 下一步

实现 Recording Panel 和真实 Qt record/export 验收。
