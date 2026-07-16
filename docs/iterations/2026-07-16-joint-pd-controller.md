# Joint Position PD Controller

日期：2026-07-16
提交：待提交

## 目标

提供可复用的平滑 joint-space position controller，并验证外部 OpenUSD 手臂的收敛、限位和确定性。

## 主要改动

- 新增 `simlab.controllers` package 和 `JointPositionPdController`。
- `JointPdConfig` 定义 target、kp、kd、max_delta 和 tolerance，拒绝非有限或非法范围。
- 每步根据 qpos error 和 qvel 计算外环 correction，并限制 position target delta。
- `set_target` 与 `set_targets` 支持 runtime goal 更新，未知 joint 不产生部分更新。
- Reset 验证 observation joint IDs 并记录 reset simulation time。
- Session 继续负责 actuator mapping/control range clamp，MuJoCo position drive 负责内环力矩。
- 增加 `examples/controllers/two_joint_pd.py`，根据 observation 前两个稳定 joint ID 相对 Home 运动。

## 验证

- 纯逻辑验证 delta bound、velocity damping、runtime target 更新和配置错误。
- 示例文件通过 ProjectControllerLoader factory/contract 验证，不硬编码 USD Prim 名称。
- 外部 USD 双关节手臂两次 200-step replay 逐样本一致，绝对误差小于 `1e-12`。
- 肩关节 qpos 大于 0.45、肘关节小于 -0.8，进入目标邻域。
- target 99 rad 时 actuator ctrl 精确 clamp 到 joint upper；qpos 满足 MuJoCo soft-limit 容差。
- 聚焦测试：4 passed；Ruff、Mypy 通过。

## 已知限制

- 这是 position-drive 外环，不是 torque-level inverse dynamics controller。
- kp/kd 为离散外环参数，尚无自动整定或 UI 参数编辑。
- 示例按 observation 顺序选择前两个 joint，生产项目应显式配置稳定 ID。

## 下一步

建立 Joint State Sensor Contract，将固定物理时钟 observation 发布为可订阅 sensor samples。
