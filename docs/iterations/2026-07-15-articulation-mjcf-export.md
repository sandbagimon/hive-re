# Articulation MJCF Export

日期：2026-07-15
提交：待提交

## 目标

把正式导入的外部 OpenUSD 机械臂转换为 MuJoCo 可编译的 articulation，为 runtime state 和控制闭环
建立真实物理模型。

## 主要改动

- Robot actor transform 输出为 articulation wrapper body，fixed base 不创建 freejoint。
- Link hierarchy 输出 nested body，局部 position 和 xyzw quaternion 转为 MJCF wxyz。
- 输出 Link inertial、primitive Collider、friction、revolute/continuous hinge 和 prismatic slide。
- 输出 joint range/axis，以及 position/velocity/motor actuator 的 ctrlrange、gain 和 force range。
- 写入 `home` keyframe，包含 robot initial joint positions；混合 scene 同时包含 freejoint 完整初态。
- 保持原 primitive/object 和 imported mesh exporter 路径不变。

## 验证

- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：62 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- 外部 fixture 编译结果：2 joints、2 actuators、无 freejoint、5 bodies。
- 混合 free body + robot 模型 `nq=9`，home keyframe 维度和值正确。

## 已知限制

- Mesh Collider 仍需逐 Link mesh cache 才能导出。
- Joint damping/frictionloss 和 full inertia 尚未映射。
- Runtime 尚未加载 home key，也未发布 joint/link/actuator state。

## 下一步

扩展 SimulationState 和 Bridge，发布 Link world pose、joint qpos/qvel、actuator ctrl，并让 viewport 用
独立 simulation transform 更新机器人 Link，不覆盖 authoring Scene。
