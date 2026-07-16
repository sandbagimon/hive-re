# Trajectory Qt E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine 页面验证外部 USD 机械臂的轨迹面板、Bridge、MuJoCo 和 viewport 完整闭环。

## 主要改动

- 扩展 opt-in Qt 测试，在 Reset Home 后通过 Jog 建立 `0.5 rad` 编辑目标。
- 从 UI 设置轨迹名称和 `0.8s` 时长并点击 Load，验证首帧 target、名称、duration 和 stopped 状态。
- 首次 Play 在中途 Pause，验证 simulation time 和 trajectory cursor 均保持冻结。
- 点击 Stop 后验证 cursor 归零，actuator ctrl 恢复 Home 首帧。
- 再次 Play 到自然完成，验证 service 自动 Paused、末帧 target、关节运动和 child Link quaternion。
- 断言完成态 DOM status、时间文本和 progress，并保存真实页面截图。

## 验证

- 显式 QtWebEngine E2E：1 passed in 8.53s。
- 完成态截图：`/tmp/simlab-robot-trajectory-completed.png`。
- 截图确认 Completed、`0.80 / 0.80 s`、最终关节目标和 viewport 姿态一致，无布局重叠。

## 已知限制

- 测试覆盖两关键帧轨迹，尚未覆盖三个以上可编辑 keyframe。
- Loop 模式已由纯 Python player 测试覆盖，Qt 页面尚未自动验证循环播放。

## 下一步

实现可编辑 Keyframe List，并将多关键帧 authoring 纳入真实 UI 验收。
