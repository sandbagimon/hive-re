# Trajectory Library Contract

日期：2026-07-16
提交：待提交

## 目标

建立可随 scene.json 保存的共享轨迹库契约，同时保持旧项目兼容。

## 主要改动

- Scene schema 增加可选 `trajectories` 数组和 trajectoryClip 定义。
- 每个 clip 包含稳定 `trajectory_*` ID、owner `actor_id` 和共享 JointTrajectory payload。
- Python 增加 SceneTrajectory model，并接入 Scene `to_dict/from_dict`。
- 空 library 不写入 JSON，旧 scene 加载后仍可原样 round-trip。
- TypeScript Scene/SceneTrajectory 类型同步更新。
- validate_scene 检查 clip ID 唯一、owner 存在且为 robot。
- 根据 actor articulation_ids 解析 position actuator joints，拒绝不属于该 robot 的 targets。

## 验证

- scene/schema/robotics/trajectory library 聚焦测试：21 passed。
- 覆盖 save/load、旧 scene、重复 ID、悬空 actor、非 robot actor和未知 joint。
- ruff、mypy、TypeScript typecheck 通过。

## 已知限制

- EditorStore 尚未提供 library 写入操作，UI draft 仍未真正保存到 scene。
- clip 暂无 description、tags 或 thumbnail 等资产元数据。

## 下一步

接入 EditorStore upsert/remove、actor 删除级联和 history 恢复。
