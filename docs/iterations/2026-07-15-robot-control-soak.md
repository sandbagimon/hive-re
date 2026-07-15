# Robot Control Soak

日期：2026-07-15
提交：待提交

## 目标

用持续变化的控制输入验证外部 OpenUSD 机械臂不会出现数值发散、关节越限或 actuator 超额输出。

## 主要改动

- 使用真实外部 `.usda` fixture 导入并编译机械臂，不绕过 OpenUSD pipeline。
- 在 2 ms timestep 下执行 40 轮交替目标，每轮 50 step，总计 2,000 step / 4 simulation seconds。
- 每轮检查 simulation time 单调递增，最终时间与固定步数一致。
- 检查所有 Link position/quaternion、joint qpos/qvel、actuator ctrl/force 均为有限值。
- 检查 Link quaternion 保持归一、joint qpos 不越 USD limits、force 不超过 USD maxForce。
- failure message 包含 cycle 和 stable Link/Joint/Actuator ID，便于定位发散来源。

## 验证

- 独立 soak：1 passed，约 1 秒。
- 完整测试门禁见提交记录。

## 下一步

实现与 UI callback 解耦的固定物理时钟和有限 catch-up。
