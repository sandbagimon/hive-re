# Runtime Robotics State

日期：2026-07-15
提交：待提交

## 目标

让 MuJoCo Session 以 Robotics stable ID 发布机械臂运行时状态，并正确加载/重置 home keyframe。

## 主要改动

- SimulationState 新增 Link pose、Joint qpos/qvel 和 Actuator ctrl/force 列表，原 actor state 保持兼容。
- Session 按 MJCF 名称映射 Robotics stable ID 到 body/joint/actuator ID。
- 初始化和 Reset 优先加载 `home` keyframe，保持外部 USD Drive target 导入的初始关节姿态。
- state 读取 MuJoCo `xpos/xquat`、qpos/qvel、ctrl 和 actuator_force，不回写 Scene.robotics。

## 验证

- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：63 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- fixture 状态包含 3 links、2 joints、2 actuators；Step 推进时间，Reset 恢复 elbow `-0.4 rad`。

## 已知限制

- TypeScript 尚未声明和消费新增 runtime 字段。
- 尚无 joint target RPC，actuator ctrl 当前保持 MuJoCo 默认值。

## 下一步

接入 TypeScript SimulationState 和 viewport Link simulation transform，然后增加 joint-position command RPC。
