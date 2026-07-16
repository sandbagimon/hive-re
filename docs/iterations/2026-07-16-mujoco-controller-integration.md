# MuJoCo Per-Step Controller Integration

日期：2026-07-16
提交：待提交

## 目标

让 Python controller 通过稳定 observation/action contract 驱动外部 OpenUSD 机械臂的每个物理步。

## 主要改动

- MuJoCo Session 和 SimulationService 增加 controller attach/detach。
- 每个 `mj_step` 前构造独立 joint/actuator observation，并执行 controller step。
- position action 复用 joint-to-actuator 映射、finite 校验和 control-range clamp。
- Session Reset 对健康 controller 重新调用 reset callback。
- Controller runtime state 发布 python mode、name、step count、duration 和 deadline。
- controller exception 或 action 拒绝进入 fault，但 MuJoCo 继续固定步长运行。
- Python controller、手动 joint targets 和 trajectory playback 明确互斥。
- 新增 `docs/CONTROLLER_API.md`，记录最小示例和生命周期。

## 验证

- 外部 USD 双关节机械臂执行 100 次 callback，observation time 为 0.00 到 0.99 秒。
- 最终 actuator ctrl 为 0.6/-1.0，肩关节产生正向运动。
- Reset 再次调用 callback 并清零 step count。
- controller 首步异常后只调用一次，physics 仍推进到 0.03 秒。
- 手动 target 与 trajectory Play 在 controller attach 时明确拒绝。
- Controller/Session 聚焦测试：20 passed；Ruff、Mypy 通过。

## 已知限制

- Desktop UI 尚无项目 Python module 选择、reload 或 detach 控件。
- action 第一版只有 position target；velocity、torque 和批量 buffer 尚未实现。
- deadline 检测不是 callback 的抢占式终止。

## 下一步

实现用户显式触发的项目 Controller Loader，并验证外部 Python 文件驱动导入机械臂。
