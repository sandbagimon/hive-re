# Joint State Recording Contract

日期：2026-07-16
提交：待提交

## 目标

建立可复现、可导出且内存有界的机械臂关节状态记录格式。

## 主要改动

- 新增 Joint State Recording JSON schema。
- manifest 记录 MuJoCo engine/version、physics timestep 和 scene version。
- sample 以 stable joint/actuator ID map 保存 qpos、qvel、ctrl 和 force。
- Python model 支持完整 `to_dict/from_dict` round-trip。
- CSV exporter 按请求的 joint_ids、actuator_ids 顺序生成确定列。
- JointStateRecorder 支持 name/selection/timestep 校验和 start/capture/stop 生命周期。
- 默认最大 100,000 samples；达到上限后停止 capture 并设置 limit_reached，不继续增长内存。
- capture 拒绝缺失 stable ID、非有限值和非严格递增 simulation time。
- TYPE_CHECKING 边界避免 recorder 与 future Session runtime 集成产生循环导入。

## 验证

- recording/schema 聚焦测试：8 passed。
- 覆盖 JSON/CSV、上限停止、缺失 ID、时间顺序、空/重复 selection。
- ruff 和 mypy 通过，mypy 检查源文件数增至 37。

## 已知限制

- Recorder 尚未由 MuJoCo Session 自动调用。
- JSON/CSV 目前只返回字符串，尚未有 Bridge 文件导出 RPC。

## 下一步

在每个 `mj_step` 后 capture，并发布 recording runtime state 与导出 RPC。
