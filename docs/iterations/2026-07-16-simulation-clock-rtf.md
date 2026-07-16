# Simulation Clock RTF Contract

日期：2026-07-16
提交：待提交

## 目标

在不改变 MuJoCo 固定 timestep 的前提下，为机械臂调试提供可验证的仿真实时因子契约。

## 主要改动

- SimulationService 支持 0.25x、0.5x、1x、2x target real-time factor。
- wall-time accumulator 按 target RTF 缩放，单次 catch-up 上限保持生效。
- SimulationState 增加 `clock.target_rtf`、`clock.actual_rtf` 和 `clock.timestep`。
- actual RTF 使用当前连续运行测量窗口内的 simulated time / wall time 计算。
- 切换倍率重置测量窗口并保留未消费 accumulator，避免重复或丢失已排队物理时间。
- EditorBridge 增加 `setSimulationSpeed` RPC；无 Session 时也可预设下一次运行速度。

## 验证

- 固定假时钟验证 0.5x 在 0.04 秒 wall time 推进 0.02 秒 simulation time。
- 固定假时钟验证 2x 在 0.04 秒 wall time 推进 0.08 秒 simulation time。
- 两种倍率下 MuJoCo timestep 均保持 0.01 秒，actual RTF 分别为 0.5 和 2.0。
- Clock 与 Bridge 聚焦测试：26 passed；Ruff 与 Mypy 通过。

## 已知限制

- TypeScript toolbar 尚未接入倍率选择与 actual RTF readout。
- actual RTF 是当前连续运行窗口平均值，暂未提供滑动窗口或性能历史图。

## 下一步

接入 TypeScript segmented control，并在真实 Qt 页面验证运行中切换速度。
