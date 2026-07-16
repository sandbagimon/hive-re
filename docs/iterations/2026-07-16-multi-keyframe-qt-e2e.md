# Multi-Keyframe Qt E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 Qt 页面验证多关键帧 authoring、MuJoCo 分段插值和 EditorStore 隔离。

## 主要改动

- 在两帧轨迹完成态点击 Add Current，验证列表从 2 帧增加到 3 帧。
- 将新增帧 time 从末尾改为 `0.4s`，断言 DOM 自动排序为 `0.0、0.4、0.8s`。
- 将中间帧 AxisA target 编辑为 `-0.4 rad`，其余 joint targets 保持完整。
- Load/Play 后在 `0.32-0.48s` 窗口断言 actuator ctrl 小于 `-0.25`，证明执行经过中间段。
- 验证末帧 target 回到 `+0.5`，trajectory 自然 Completed 且 simulation Paused。
- 删除中间帧后验证列表恢复两帧。
- Add/Edit/Delete 前后对比 dirty、canUndo、canRedo，确认临时 draft 不污染 Scene history。

## 验证

- 显式 QtWebEngine E2E：1 passed in 10.72s。
- 三关键帧截图：`/tmp/simlab-multi-keyframe.png`。
- 截图确认时间、AxisA/AxisB targets、Completed 进度、最终 viewport pose 和滚动布局一致。

## 已知限制

- draft 关闭项目后丢失，尚未进入 scene/project persistence。
- 最终 target 到达时 fixed clock 自然停止，不额外等待 position servo 完全静态收敛。

## 下一步

建立 trajectory library 的共享 Scene schema，并将显式保存的 draft 接入 dirty/undo/redo。
