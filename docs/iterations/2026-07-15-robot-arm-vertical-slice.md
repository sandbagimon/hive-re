# Robot Arm Vertical Slice

日期：2026-07-15
提交：未提交

## 目标

将 Gate 1 的短期演示目标从 OpenUSD 小车改为外部 OpenUSD 机器人手臂：用户从磁盘加载带
articulation 的机械臂资产，在 MuJoCo 中运行物理仿真，并从编辑器操作各关节。

## 路线变更

- 保留 Robotics Intermediate Model 作为第一项工程任务。
- 第一版 fixture 改为 fixed base、至少三个 link、两个 revolute joint 和两个 position actuator。
- Gate 1A 改为导入 OpenUSD 机械臂的层级、碰撞、惯性、关节和 drive。
- Gate 1B 改为验证关节驱动、重力、限位、碰撞及 link/joint runtime state。
- Gate 1C 改为关节空间 position control，UI 提供 slider、数值目标和 qpos/qvel 反馈。
- IK、末端位姿拖拽、轨迹规划、抓取器和 torque control 不进入首个闭环。
- 产品验收必须使用外部 USD 文件走公开 Import USD 路径；不得内置机械臂或针对 fixture 的 Prim
  名称、拓扑和目录结构编写特判。

## 验收目标

```text
从磁盘导入外部 OpenUSD 机器人手臂资产
-> 保留 Robot/Link/Joint 层级
-> 转换并编译 MJCF
-> 固定步长运行 MuJoCo
-> UI 修改至少两个关节目标
-> 手臂在关节限位、重力和碰撞约束下运动
-> viewport 与 inspector 同步 link pose、qpos/qvel
-> 保存重开后结构、home pose 和控制配置一致
```

## 已知限制

- 首版只承诺 fixed base 和 revolute joint 的完整演示。
- 首版操作方式是关节空间 position control，不承诺 IK 或 Cartesian control。
- 机器人资产来源和许可证仍需在 fixture 子任务中明确。
- 程序生成 USD 可用于单元测试，但不能替代外部文件的端到端导入验收。

## 下一步

实现版本化 Robotics Intermediate Model 和 `shared/schemas/robotics.schema.json`，使用最小机械臂
fixture 完成 schema validation、Python round-trip 和旧 Scene 兼容测试；暂不修改 importer、exporter
或 UI。这里的 JSON fixture 仅验证中间模型；下一轮必须使用外部 USD 文件验证通用 Prim/Physics
映射和资源依赖解析。
