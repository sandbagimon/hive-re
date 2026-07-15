# Runtime Link Viewport Sync

日期：2026-07-15
提交：待提交

## 目标

让 TypeScript editor 消费 Python 发布的机器人 runtime state，以独立 simulation transform 更新 Link，
不覆盖 Scene.robotics authoring 数据。

## 主要改动

- TypeScript SimulationState 增加 Link pose、Joint qpos/qvel 和 Actuator ctrl/force 类型。
- Bridge Protocol schema 将 links/joints/actuators 纳入 simulation state 必填字段。
- viewport 保存 stable link ID 到 three.js Group 映射。
- MuJoCo world pose 通过父 Group world transform 逆变换为 Link local pose，再更新嵌套层级。
- simulation 结束时沿用既有 `setViewportScene()` 路径，从 authoring scene 完整重建姿态。
- checked-in generated viewport JavaScript 与 TypeScript 源同步。

## 验证

- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：63 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- Bridge Protocol Draft 2020-12 schema 校验通过。
- 当前环境没有 Node.js/npm 和显示服务，未执行 TypeScript 编译及真实 QWebEngine 截图。

## 下一步

实现 stable joint ID 到 MuJoCo position actuator 的 command RPC、限位和 Reset home target。
