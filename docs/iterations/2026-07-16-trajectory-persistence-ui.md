# Trajectory Persistence UI

日期：2026-07-16
提交：待提交

## 目标

让用户从 Trajectory Panel 将 draft 保存为 Scene clip，并切换、更新或删除已保存轨迹。

## 主要改动

- Panel 增加 saved clip selector、Save 和 Delete controls。
- New Clip 与已保存 clip 明确分离；Save 首次创建稳定 ID，后续更新同一 ID。
- JointTrajectory payload 可 hydrate 为带稳定 keyframe UI ID 的 editable draft。
- 每个 draft state 记录 clip ID、home signature 和 source signature。
- Scene clip 因 undo/redo 改变时自动 hydrate；普通 runtime render 不覆盖本地未保存编辑。
- 删除 clip 后保留缺失 source identity，Undo 恢复时可重新选中并 hydrate 原 payload。
- New/Open 清空 draft cache，避免相同 actor ID 在项目之间串数据。
- Save/Delete 使用 EditorStore history，前端按钮只负责验证与状态选择。

## 验证

- TypeScript build、EditorStore test 和 TrajectoryDraft test 通过。
- web viewport 静态测试：2 passed。
- 原 multi-keyframe Qt E2E：1 passed in 10.51s。
- 检查真实截图，selector、单行 Save、Delete 和 keyframe list 在 286px Inspector 内可用。

## 已知限制

- 尚未通过真实文件 Save/Open 自动验证 clip 恢复。
- UI 当前不支持复制 clip 或跨 robot 迁移 targets。

## 下一步

增加项目文件 Save/Open E2E，并在重开后运行恢复的轨迹。
