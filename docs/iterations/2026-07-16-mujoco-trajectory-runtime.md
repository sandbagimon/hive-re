# MuJoCo Trajectory Runtime

日期：2026-07-16
提交：待提交

## 目标

让 stable joint trajectory 在 MuJoCo 固定物理步中执行，并通过 Python RPC 发布完整播放状态。

## 主要改动

- MuJoCoSimulationSession 内置 JointTrajectoryPlayer，并按 position actuator joint ID 验证轨迹。
- Load 将 actuator ctrl 定位到首帧，Play 从当前 simulation time 建立 cursor 起点。
- 每个 `mj_step` 前采样轨迹，确保 callback 合并多个 physics step 时仍逐步插值。
- 每批 step 后采样最终 simulation time，确保 duration 边界精确应用最后 target。
- 手工 setJointTargets 会 Pause 正在播放的轨迹，避免下一 physics step 静默覆盖 Jog。
- Reset 保持物理 Home 语义，同时将已加载 trajectory cursor 停到 0。
- SimulationState 增加 trajectory status/time/duration/name，共享 Bridge schema 同步更新。
- SimulationService 提供 load/play/pause/stop，Play 启动 fixed clock，Pause/Stop 停止 clock。
- 非 loop 轨迹自然完成后 Service 停止 running，Bridge 停 QTimer 并发布 Paused。
- EditorBridge 提供 `loadTrajectory`、`playTrajectory`、`pauseTrajectory`、`stopTrajectory` RPC。

## 验证

- Session/clock/schema 聚焦测试：17 passed。
- Bridge + Session 聚焦测试：18 passed。
- 验证 0.5 秒轨迹完成、末帧 ctrl、关节运动、Pause cursor、Stop 首帧和未知 joint 拒绝。
- 验证 Bridge fixed-clock 自然完成后 timer inactive、service running=false、status Paused。
- TypeScript typecheck/build、ruff、mypy 通过。

## 下一步

实现 TypeScript Trajectory Panel、进度反馈和用户可操作的最小轨迹生成。
