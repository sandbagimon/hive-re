# OpenUSD Robot Fidelity and Franka Control Gate

日期：2026-07-30  
提交：待提交

## 目标

解决复杂 OpenUSD 机器人导入后姿态异常、部件不完整和 MuJoCo mesh 编译失败的问题，使
OpenUSD、BeeFoundrySim Robotics Model、Three.js 和 MJCF/MuJoCo 对关节坐标系与初始状态采用同一
语义，并用 Franka Panda 完成真实资产验证和控制入口。

## 主要改动

- Robotics Model v2 同时保存 `parent_frame` 和 `child_frame`，不再把 USD Joint 两侧的
  `physics:localPos0/localRot0` 与 `localPos1/localRot1` 合并成单一 origin。
- 规范化关节零位为
  `T_parent_child(q) = T_parent_joint * Motion(axis_joint, q) * inverse(T_child_joint)`；
  Three.js 预览与 MJCF 导出共用这一约定。
- 将 `JointStateAPI` 的 position/velocity 作为初始状态，将 Drive targetPosition/
  targetVelocity 作为控制目标，避免导入时用 Drive Target 篡改机器人 authored pose。
- MJCF 导出时把 joint-frame axis 正确转换到 child body frame，并保持 revolute、continuous、
  prismatic 和 fixed joint 的兼容路径。
- 为 mesh collider 生成逐 Link OBJ cache，修复 MuJoCo 报告 `must have valid meshid` 的空
  mesh geom 问题。
- 改进 OpenUSD mesh 提取、缩放、碰撞/视觉分离和稳定 ID 映射；旧 Robotics v1 场景继续走
  legacy origin 兼容路径。
- 接入高精度 Franka Panda 项目资产：11 个 Link、10 个 Joint、29 个视觉 Mesh、12 个
  MuJoCo mesh collider。
- 增加 `franka_joint1_wave.py` 示例 Controller，通过稳定关节 ID 对 panda_joint1 执行限位内
  正弦位置控制。
- 完善 `start_backend.sh`：同时启动 REST API 与算法 gRPC 后端，检查依赖、端口、健康状态，
  并在任一进程结束时统一清理。
- 增加 `start_frontend.sh`：验证 Node/npm 与依赖，配置 Vite 到远端 API 的代理目标。

## 验证

- Franka 视觉缓存保持 29 个几何、120,497 个顶点和 131,949 个三角面，未发生几何丢失。
- 关节双帧、axis 转换、初始位置/速度、Drive Target 分离和旧 v1 round-trip 均有单元测试。
- mesh collider fixture 可导出带有效 mesh asset 的 MJCF，并由 MuJoCo 成功编译。
- Three.js canonical link pose 与后端关节状态同步测试通过。
- Python 非端口回归 232 passed、3 skipped；Ruff、Mypy、TypeScript 和生产构建通过。

## 已知限制

- 当前 Franka quality USD 保留完整几何和物理层级，但没有把 Omniverse OmniPBR/MDL 的完整
  Shader Graph 转换成 Web 材质；缺失纹理时仍使用 display color/default material 回退。
- 视觉 Mesh 使用原始高精度拓扑，碰撞 Mesh 尚未做自动凸分解或低模化。
- Controller 示例只控制一个关节，不包含末端执行器 IK、抓取任务或安全速度规划。
- MuJoCo 与 PhysX 的材质、接触和 Drive 参数不能逐字段直接等价，当前只转换已声明的受支持子集。

## 下一步

- 为 Franka 增加语义关节组、gripper action 和末端位姿任务。
- 增加 collision decimation/convex decomposition，并把视觉与碰撞质量作为显式导入选项。
- 建立 UsdPreviewSurface 多材质/纹理打包与缺失依赖修复流程。
- 用真实 Controller 完成 Reset、Run、Stop、trajectory 与 Gym task 的 Franka E2E。
