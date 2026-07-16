# TypeScript Simulation Speed Toolbar

日期：2026-07-16
提交：待提交

## 目标

让用户从编辑器直接控制机械臂仿真速度，并看到实际达到的实时因子。

## 主要改动

- Command bar 增加 0.25x、0.5x、1x、2x segmented control。
- active segment 始终由 Python 返回的 `clock.target_rtf` 确认。
- RPC 失败时恢复之前选项并显示错误 toast。
- actual RTF readout 使用 `clock.actual_rtf`，随 runtime state 局部更新。
- TypeScript Bridge 类型和 Editor Automation API 增加 `setSimulationSpeed`。
- speed 控件使用固定宽度，窄屏时随 command bar wrap，不改变 workspace 尺寸。

## 验证

- TypeScript build 和 frontend tests 通过。
- Clock/Bridge/web 聚焦测试：28 passed。
- 真实 QtWebEngine robot/trajectory/recording E2E：1 passed。
- 1360x860 截图显示 1x active、actual RTF 约 0.99x，无重叠或横向溢出。

## 已知限制

- 尚未在真实 Qt 页面自动切换 0.5x/2x 并核对 simulation time 比例。
- actual RTF 为当前连续运行窗口平均值，没有历史曲线。

## 下一步

增加 Simulation Speed Qt E2E，覆盖运行中倍率切换和固定步 recording 连续性。
