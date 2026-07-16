# Trajectory Save/Open/Replay Qt E2E

日期：2026-07-16
提交：待提交

## 目标

验证外部 USD 机械臂轨迹从 authoring 到真实项目文件，再到新窗口 MuJoCo replay 的完整生命周期。

## 主要改动

- 在真实页面重新创建 `0.0、0.4、0.8s` 三帧 draft 并点击 Save。
- 验证 Scene 生成 `trajectory_001`，中间 AxisA target 为 `-0.4`。
- UI Undo 删除 clip、Redo 恢复 clip，并验证三帧 draft 自动 hydrate。
- 通过 automation path RPC 写入真实 scene.json，断言 dirty=false 和 currentPath 同步。
- 读取落盘 JSON，验证 trajectory name、owner、times 和 targets 保真。
- 关闭首个 MainWindow，创建第二个窗口并显式打开保存文件。
- 验证 saved clip selector、三帧 time/target 和外部 USD robot hierarchy 恢复。
- 在新窗口 Load/Play 恢复轨迹，MuJoCo 自然完成并发布最终 actuator target。

## 验证

- 双窗口显式 QtWebEngine E2E：1 passed in 14.30s。
- 重开截图：`/tmp/simlab-trajectory-reopened.png`。
- 截图确认 selector、keyframes、Completed 状态、关节反馈和 viewport pose 一致。

## 已知限制

- project scene name 仍沿用当前 Untitled Scene，尚无独立 rename project workflow。
- clip library 暂无导入/导出单个轨迹文件的 UI。

## 下一步

建立 joint state recording contract 和 JSON/CSV 数据导出。
