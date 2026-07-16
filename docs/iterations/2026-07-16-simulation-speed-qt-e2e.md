# Simulation Speed Qt E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine 机械臂工作流中验证仿真倍率、轨迹和固定步录制共享同一物理时钟。

## 主要改动

- 双窗口测试重开保存的外部 OpenUSD robot scene 与三关键帧轨迹。
- 通过 toolbar 点击 0.5x，在受控 0.04 秒 wall time 内验证推进 0.02 秒。
- 运行中点击 2x，在相同 wall time 内验证再推进 0.08 秒。
- 核对 active segment、actual RTF `2.00x` 和固定 0.01 秒 timestep。
- 同一 recording 覆盖倍率切换，验证 0.00 到 0.10 秒共 11 个无重复、无漏步样本。
- fake clock 验收后恢复 monotonic clock，继续完成自然回放和 JSON/CSV 导出。

## 验证

- 真实 QtWebEngine 双窗口 E2E：1 passed in 16.00s。
- 0.5x actual RTF 为 0.5，2x actual RTF 为 2.0。
- recording times 等于 `[0.00, 0.01, ..., 0.10]`。
- 后续 1x 完整轨迹与 recording export 回归保持通过。

## 已知限制

- actual RTF 仍是连续运行窗口平均值，没有滑动窗口性能图。
- 速度 preset 固定为四档，暂不接受任意倍率输入。

## 下一步

建立 per-step Controller API，让用户代码能够消费 joint observation 并输出 position targets。
