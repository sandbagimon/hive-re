# Live Joint Jog

日期：2026-07-15
提交：待提交

## 目标

让用户能以确定的小步长调试外部机械臂关节，并在运行过程中持续看到真实 qpos/qvel 反馈。

## 主要改动

- Joint Control 增加 step size，默认 0.05 rad，可在 0.001 到 1 rad 之间配置。
- 每个 position joint 增加减/增 Jog 按钮，按当前 actuator ctrl 计算下一目标。
- Jog、range、number 和 Home 全部复用 `setJointTargets`，后端继续执行原子验证和限位。
- step size 同步到 range/number 的 HTML step，输入聚焦时可用原生方向键调整。
- 新增局部 runtime inspector updater，每帧刷新 controller、qpos/qvel 和 actuator ctrl。
- runtime 更新不会重建 Inspector，也不会覆盖当前获得焦点、尚未提交的输入。
- Jog 按钮使用固定尺寸和 tooltip，紧凑面板不会因动态数值发生布局漂移。

## 验证

- TypeScript typecheck 和正式 build 通过，checked-in generated JavaScript 已更新。
- 静态 UI contract 测试覆盖 Jog 和 runtime updater。
- 完整 Python、frontend、ruff、mypy 门禁见提交记录。

## 下一步

让 Scene Tree 中的 Joint 可选择，并在 Inspector/viewport 聚焦对应 child Link。
