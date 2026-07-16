# Trajectory Draft Model

日期：2026-07-16
提交：待提交

## 目标

建立与 DOM、EditorStore 和 Python Bridge 解耦的 TypeScript 关键帧编辑模型。

## 主要改动

- 新增 TrajectoryDraft 与带稳定 UI ID 的 EditableTrajectoryKeyframe。
- 支持创建 Home/End 初始帧、整体时长缩放、捕获新帧和按 time/ID 稳定排序。
- 支持单帧时间、单 joint target 编辑和删除，删除时保护最少两帧约束。
- 前端校验镜像 Python player：首帧从 0 开始、时间严格递增、joint ID 集合一致且数值有限。
- 只有通过校验的 draft 才能转换为不含 UI ID 的共享 JointTrajectory payload。
- frontend test 脚本加入 draft 模型单元测试。

## 验证

- TypeScript build 通过。
- EditorStore frontend test 通过。
- TrajectoryDraft capture/sort/edit/validation frontend test 通过。

## 已知限制

- 当前是纯数据层，Trajectory Panel 尚未渲染和操作 keyframe rows。
- draft 仅驻留内存，尚未随 project 保存。

## 下一步

将 draft model 接入面板，并验证编辑不会修改 Scene dirty/undo 状态。
