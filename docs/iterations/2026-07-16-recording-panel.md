# TypeScript Recording Panel

日期：2026-07-16
提交：待提交

## 目标

让机械臂用户从编辑器直接选择关节、开始/停止记录并导出数据。

## 主要改动

- Robot Inspector 增加独立 Recording section，非 robot actor 自动隐藏。
- 默认选择当前 robot 的全部 position joints，并映射对应 actuator IDs。
- 名称和 selection 保存在 per-actor 临时 draft，不修改 Scene dirty/history。
- Start 调用 startRecording，暂停态首次使用会创建 Session，运行态不会中断 simulation。
- Stop 仅停止 recorder，不改变当前 simulation Running/Pause 状态。
- Header 实时显示 Idle、Recording sample count、Stopped samples 或 Limit。
- runtime sample count 通过局部 DOM 更新，不重建 Inspector、Trajectory 或 Scene Tree。
- Export JSON/CSV 使用 Python 原生 Save dialog；无 recording 或活动 recording 时禁用。
- New/Open 清空 recording draft cache，避免跨项目 selection 泄漏。

## 验证

- TypeScript build 和 frontend tests 通过。
- Bridge/schema/web tests：16 passed。
- 双窗口 trajectory Qt 兼容 E2E：1 passed in 14.36s。
- 检查真实截图，Recording controls 在 286px Inspector 内无重叠或文本溢出。

## 已知限制

- 尚未在真实 Qt 页面自动点击 Start/Stop 和核对 export 内容。
- 当前 selection 粒度为 joint，并自动包含配套 position actuator。

## 下一步

增加 Recording Qt E2E，验证 live count 和 JSON/CSV artifact。
