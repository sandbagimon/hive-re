# Joint Trajectory Contract

日期：2026-07-16
提交：待提交

## 目标

建立不依赖 UI 和 MuJoCo 的机械臂轨迹数据契约与确定性时间语义。

## 主要改动

- 新增 `joint-trajectory.schema.json`，定义 version、name、loop 和至少两个 keyframe。
- Keyframe 使用非负 time 与 stable joint ID 到 target 的对象映射。
- Python model 支持 JSON round-trip、duration 和 joint ID 集合。
- 验证要求首帧 time=0、时间严格递增、每帧 joint 集合一致、target 全部有限。
- 可选 allowed joint set 会拒绝没有 position actuator 的未知 joint。
- JointTrajectoryPlayer 支持 stopped、playing、paused、completed 四种状态。
- 播放器以传入 simulation time 计算 cursor，不读取墙钟。
- Keyframe 间按每个 joint 线性插值；Loop 使用 duration 取模。
- Pause 保留 cursor，Resume 从同一位置继续；Stop 回到首帧。

## 验证

- 轨迹与 schema 聚焦测试：10 passed。
- 覆盖 round-trip、少于两帧、非零起点、非递增、joint 缺失、NaN、未知 joint。
- 覆盖插值、Pause/Resume、Complete、Stop 和 Loop。
- ruff、mypy 通过，mypy 检查范围增加到 35 个 source files。

## 下一步

将播放器接入 MuJoCo physics step、SimulationState 和 Bridge RPC。
