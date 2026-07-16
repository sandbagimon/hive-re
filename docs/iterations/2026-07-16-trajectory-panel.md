# TypeScript Trajectory Panel

日期：2026-07-16
提交：待提交

## 目标

让用户在机械臂 Inspector 中生成最小关节轨迹，并通过现有 Python Bridge 操作 MuJoCo 播放器。

## 主要改动

- Robot Inspector 增加紧凑的 Trajectory 区域，包含名称、时长、循环、进度和播放状态。
- 从导入关节的 initial position 与当前 actuator target 生成两关键帧轨迹。
- Load、Play、Pause、Stop 直接调用 Bridge trajectory RPC，并展示 validation 错误。
- runtime state 使用局部 DOM 更新进度、时间和按钮状态，不重建 Scene Tree 或 Inspector。
- TypeScript 共享类型增加 JointTrajectory 和 keyframe 契约。
- 非 robot actor 不显示 Trajectory 区域，保持 primitive 编辑界面简洁。

## 验证

- TypeScript typecheck、build 和 frontend test 通过。
- Python tests：96 passed，2 skipped。
- ruff、mypy、git diff check 通过。
- 真实 QtWebEngine offscreen 测试：1 passed；外部 USD 机械臂完成 Run/Jog/Pause/Reset。
- 检查 1360x860 静止态和运行态截图，Trajectory、Joint Inspector、viewport 无重叠或截断。

## 已知限制

- 当前仅生成 Home 到当前 actuator target 的两关键帧轨迹，还没有可编辑 keyframe 列表。
- 尚未在真实 Qt 页面自动点击并断言 trajectory 全套控制。

## 下一步

增加 Trajectory Qt E2E，覆盖自然完成、Pause、Stop 和 viewport/runtime 同步。
