# Controller Qt E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine 页面验证项目 Python controller 的加载、运行、Reload、故障隔离和 Detach 闭环。

## 主要改动

- 双窗口测试重开保存的外部 OpenUSD robot scene 和 trajectory。
- automation 显式加载 project-root 内 controller 文件，核对 Panel name/path。
- attach 后验证 manual Jog 与 Trajectory Play disabled。
- fake clock 推进 8 个固定步，核对 step count、duration 和 actuator ctrl 0.3/-0.7。
- 同路径重写源码并点击 Reload，新 target 0.6/-1.0 在下一轮 8 steps 生效。
- Reload 抛异常版本，验证 Panel fault、错误消息和 physics time 继续推进。
- Detach 统一暂停 SimulationService/QTimer，恢复 manual Jog 与 Trajectory Play。
- controller 验收后 Reset，继续原 speed/trajectory/recording/export 回归。

## 验证

- 真实 QtWebEngine 双窗口 E2E：1 passed in 18.10s。
- Loader/Run/Reload/Fault/Detach 全部经过 TypeScript -> QWebChannel -> Python -> MuJoCo。
- controller fault 时 simulation status 保持 running，time 从 0.16 推进到 0.18 秒。
- Detach 后 simulation status 为 paused，manual controls 恢复 enabled。

## 已知限制

- Panel 仍依赖外部编辑器修改 Python 源码。
- Controller API 只有 position action，尚无参考 PD controller。
- controller fault 没有独立 traceback 展开视图，当前通过 runtime message/Console 呈现摘要。

## 下一步

提供可配置 Joint PD Controller 和项目示例，验证机械臂平滑收敛与 deterministic replay。
