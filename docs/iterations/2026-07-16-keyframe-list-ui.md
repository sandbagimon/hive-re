# Editable Keyframe List UI

日期：2026-07-16
提交：待提交

## 目标

让用户在 Trajectory Panel 中直接创建和编辑多关键帧机械臂轨迹。

## 主要改动

- 每个 robot actor 使用独立 TrajectoryDraftState，robot joint topology 变化时自动重建。
- 面板显示 keyframe 数量、稳定序号、time 和每个 position joint 的 target。
- Add Current 在末帧后增加 `0.5s`，捕获当前 actuator targets 并稳定排序。
- 非首帧 time 可编辑；首帧锁定在 0，保持 player 契约。
- target 输入使用 actuator control range，支持逐 joint 精确编辑。
- Delete 禁止删除首帧，并在只剩两帧时禁用，避免制造不可播放 draft。
- 修改总 duration 会按比例缩放所有非首帧 time。
- 未主动编辑 targets 时，Load 仍自动捕获当前目标，兼容原两帧操作路径。
- draft 不写入 EditorStore scene，因此不会改变 project dirty 或 undo/redo history。

## 验证

- TypeScript build 和 frontend tests 通过。
- web viewport 静态资源测试：2 passed。
- 真实 QtWebEngine 原轨迹闭环：1 passed in 8.54s。
- 检查静止态和 Completed 截图，播放控件、滚动 Inspector 和 viewport 无重叠。

## 已知限制

- keyframe draft 尚未保存进 project 文件。
- 尚未在 Qt 测试中自动操作 Add Current、time/target 编辑和 Delete。

## 下一步

增加多关键帧真实 UI E2E，验证 authoring、插值与 dirty 隔离。
