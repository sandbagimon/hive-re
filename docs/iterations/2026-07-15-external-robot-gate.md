# External Robot Gate

日期：2026-07-15
提交：待提交

## 目标

证明外部 OpenUSD 机械臂可以跨越项目缓存、Scene 保存重开、MJCF 和 MuJoCo runtime，完成可见、
有限位且可恢复 Home 的关节运动。

## 主要改动

- 新增 Gate 1 自动化工作流，从外部 `.usda` 导入开始，不使用手工构造的 Robotics JSON。
- 验证项目缓存中的 USD source 存在，Scene round-trip 不丢失 robotics 或 actor properties。
- 验证 shoulder/elbow target 进入 MuJoCo，关节稳定到目标附近且 Link world pose 发生变化。
- 验证越界 command 被 actuator range 限幅，Reset 恢复 joint qpos 和 actuator ctrl Home。
- MJCF 增加 `<compiler angle="radian">`，避免弧度限位被 MuJoCo 当作角度再次转换。
- 对每个直接相连的 Link 输出 contact exclude，防止关节两侧 collider 把 articulation 锁死。
- position actuator 输出 USD drive damping 对应的 `kv`，抑制持续振荡。

## 验证

- 外部机械臂 workflow、MJCF exporter、simulation session 聚焦测试：13 passed。
- 完整 Python、ruff、mypy 门禁见提交记录。

## 下一步

增加 command 原子性、controller watchdog/fault 状态和短时 soak test。
