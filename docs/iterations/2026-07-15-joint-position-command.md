# Joint Position Command RPC

日期：2026-07-15
提交：待提交

## 目标

建立 stable joint ID 到 MuJoCo position actuator 的安全控制边界，为机械臂关节 UI 提供 RPC。

## 主要改动

- MJCF home keyframe 同时写入 qpos 和 position actuator ctrl。
- Session 建立 joint ID 到 position actuator ID 映射，提供 `set_joint_position_targets()`。
- 目标必须有限，并使用 MuJoCo actuator ctrlrange 限幅；未知或无 position actuator 的 joint 返回错误。
- SimulationService 和 QWebChannel 新增 `setJointTargets(scene, targets)`，无 Session 时按当前 Scene 创建。
- 命令后立即发布 SimulationState，不修改 RoboticsModel initial_position。
- Bridge Protocol 和 TypeScript PythonBridgeObject 声明新 RPC。

## 验证

- 定向测试：13 passed。
- shoulder `99 rad` 被限幅到 `π/2`，elbow `-1` 写入 ctrl，step 后 qpos 朝目标变化。
- Reset 恢复 elbow qpos 与 ctrl 到 `-0.4 rad`；未知 joint 被拒绝。
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：64 passed，1 skipped。
- ruff、mypy 和 `git diff --check` 通过。

## 下一步

在 robot Property Panel 增加 joint slider、目标值、qpos/qvel 反馈和 Home 控制。
