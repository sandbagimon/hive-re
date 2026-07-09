# Simulation State Bridge

日期：2026-07-09

## 目标

推进 Iteration A，让 MuJoCo 不再只是导出后的 headless 日志，而是成为 viewport 的实时状态来源。

## 主要改动

- 新增 `MuJoCoSimulationSession`：
  - 将当前 scene 导出为 MJCF。
  - 在进程内加载 `MjModel` 和 `MjData`。
  - 支持 `step()`、`reset()` 和当前 `state()`。
  - 按 SimLab actor id 读取 MuJoCo body pose。
- 新增 `SimulationState` 和 `ActorSimulationState` 数据结构。
- 改造 `SimulationService`：
  - 从子进程 runner 改为 in-process session 管理。
  - 支持 Run/Pause/Step/Reset。
  - 将基础 simulation event 写入 Console。
- 改造 MJCF exporter：
  - primitive body name 使用稳定的 actor id。
  - primitive body 增加 `freejoint`，让 MuJoCo step 后可产生 runtime pose。
- 改造主窗口 toolbar：
  - 增加 Pause Simulation。
  - 增加 Step Simulation。
  - 增加 Reset Simulation。
  - 使用 `QTimer` 推进 simulation frame。
- 扩展 three.js viewport：
  - 新增 `setSimulationStateFromJson()`。
  - 新增 `clearSimulationState()`。
  - simulation pose 覆盖 viewport mesh 显示。
  - Reset 后恢复 authoring transform。
- 更新 README 和产品计划。
- 新增 simulation session 测试。

## 验证

- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m pytest`：`10 passed`。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m ruff check .`：通过。

## 已知限制

- 现在是基础实时 pose sync，不是完整 MuJoCo-native renderer。
- stepping 由 UI 线程上的 `QTimer` 驱动，大场景或高频仿真后续需要 worker/thread 策略。
- simulation overlay 还很轻量，目前只在 viewport HUD 显示 simulation time。
- Run/Pause/Reset 的按钮状态还没有动态禁用或高亮。
- authoring state 和 runtime state 已初步分离，但后续仍需要更正式的状态机。

## 下一步

- 增加 simulation overlay 和更明确的 toolbar 状态。
- 加入速度控制和 timeline。
- 在 viewport 中区分 authoring mesh 和 runtime pose 显示。
- 开始 Iteration B：rotate/scale gizmo、selection outline、frame selected、camera shortcuts。
