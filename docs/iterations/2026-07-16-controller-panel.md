# TypeScript Controller Panel

日期：2026-07-16
提交：待提交

## 目标

让用户从 robot Inspector 显式加载、观察、重载和卸载项目 Python controller。

## 主要改动

- Robot Inspector 增加独立 Controller section，非 robot actor 自动隐藏。
- Panel 显示 loaded name/path、ready/active/fault、step count 和 last callback duration。
- Load 使用原生 Python file dialog；Reload 复用当前显式 path；Detach 恢复 manual mode。
- Load/Reload 前调用 trusted-code confirm，Scene Open 不触发 controller RPC。
- runtime state 仅局部更新 status/metrics，不重建 Scene Tree、Trajectory 或 viewport。
- Python mode 禁用 manual Jog/target/Home 和 trajectory Play；后端互斥检查继续兜底。
- New/Open/stopped 清除 metadata，controller 不写入 Scene 或 dirty/history。
- Editor Automation API 增加显式 controller path load，为真实 Qt E2E 提供入口。

## 验证

- TypeScript build 和 frontend tests 通过。
- Bridge/Web/Loader 聚焦测试：20 passed；Ruff 通过。
- 真实 QtWebEngine robot/trajectory/recording 兼容 E2E：1 passed in 15.84s。
- 1360x860 Inspector 中 identity、metrics 和三按钮无溢出或重叠。

## 已知限制

- 尚未在真实页面自动加载 controller 并运行/reload/fault/detach。
- Panel 不提供源码编辑器；controller 文件由外部编辑器维护。
- trusted-code confirm 不是安全沙箱。

## 下一步

增加 Controller Qt E2E，覆盖运行、reload、fault containment 和 detach 后手动控制恢复。
