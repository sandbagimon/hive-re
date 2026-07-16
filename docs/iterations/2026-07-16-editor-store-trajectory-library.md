# EditorStore Trajectory Library

日期：2026-07-16
提交：待提交

## 目标

让 trajectory clips 成为可撤销、可保存的 Scene authoring 数据。

## 主要改动

- EditorStore 增加 `upsertTrajectory`，首次保存生成最小可用 `trajectory_001` ID。
- 传入已有 ID 时原位更新 clip，不创建重复项。
- 增加 `removeTrajectory`，空 library 会从 Scene 删除以保持紧凑 JSON。
- 保存和删除 trajectory 复用 Scene commit/history，正确更新 dirty、undo 和 redo。
- trajectory 操作保留当前 selected joint，避免保存动作打断机械臂编辑上下文。
- 删除 robot actor 时级联删除其所有 trajectory clips。
- ID 生成扫描已用编号，支持删除后的稳定最小空位复用。

## 验证

- TypeScript build 通过。
- EditorStore frontend test 覆盖 save/update/undo/redo/remove/cascade 并通过。
- TrajectoryDraft frontend test 保持通过。

## 已知限制

- 面板尚未提供 Save Clip、clip selector 和 Delete Clip。
- loadScene/undo/redo 后的 draft hydrate 尚未接入。

## 下一步

接入 Trajectory Panel persistence controls 和 draft hydration。
