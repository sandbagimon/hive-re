# Recording Qt E2E and Export Verification

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine 页面验证外部 OpenUSD 机械臂的轨迹、固定步录制和数据导出闭环。

## 主要改动

- Editor Automation API 增加读取 recording 和显式路径 JSON/CSV 导出入口。
- 双窗口 E2E 保存并重开三关键帧轨迹，只选择 AxisA 后开始录制并播放到自然完成。
- 验证 recording joint/actuator selection、样本数量、有限数值和严格 0.01 秒时间间隔。
- 自动读取 JSON/CSV artifact，核对 manifest、样本内容、列顺序和行数。
- 每个 `mj_step` 后、录制采样前同步轨迹目标，保证终点 target 不会被状态查询抢先截断。
- Recording panel 完成态截图验证 1360x860 下无溢出或遮挡。

## 验证

- Session 轨迹与录制组合回归通过，最终 actuator target 与末关键帧一致。
- 真实 QtWebEngine 双窗口 E2E：1 passed，记录 81 samples。
- JSON 时间范围 0.00 到 0.80 秒，CSV 数据行数与 artifact sample count 一致。
- 完成态截图：`/tmp/simlab-record-e2e-completed.png`。

## 已知限制

- recording 目前按每个 physics step 全量采样，尚无 decimation 或持续流式写盘。
- 实时因子和播放速度尚无 UI 控制。

## 下一步

实现 Simulation Speed / Real-Time Factor 控制，并验证不同速度下轨迹时间和 recording 时间戳仍由固定物理时钟驱动。
