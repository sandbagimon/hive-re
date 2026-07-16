# Qt Robot Control E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 TypeScript UI 中通过 Run、Jog、Pause 和 Reset 操作外部 OpenUSD 机械臂，证明完整控制体验。

## 主要改动

- QtWebEngine E2E 点击正式 Run 按钮，等待 QTimer/fixed-clock 发布 runtime state。
- 将 selected joint step 改为 0.5 rad，点击正式 Jog positive 按钮发送 setpoint。
- 运行中 setJointTargets 保持 frontend Running status，与仍在运行的 Python timer 一致。
- 验证 controller active、actuator ctrl=0.5、qpos>0.1 和 child Link quaternion 变化。
- 验证 Joint Inspector position 已由局部 DOM updater 刷新，不是静态 authoring 值。
- 点击 Pause 后等待 200 ms，验证 simulation time 不再推进。
- 点击 Reset 后验证 time=0、controller ready 和 shoulder Home qpos。
- Preflight 将引用有效 articulation 的 robot actor 计入 physics actor。
- Robot actor 缺少或引用未知 articulation 时发布结构化 error，避免静默导出空模型。
- 运行态截图人工确认 robot pose、outline、qpos/qvel、target 和 Running badge。

## 验证

- Qt Run/Jog/Pause/Reset E2E：1 passed，约 6 秒。
- Physics preflight + Bridge 聚焦测试：16 passed。
- 运行态截图：`/tmp/simlab-robot-joint-running.png`。
- 截图中不再存在错误的 `NO_PHYSICS_ACTORS` warning。

## 下一步

建立 stable joint ID trajectory schema 和固定时钟播放器。
