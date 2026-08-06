# Quadrotor Propulsion and Control

日期：2026-08-03  
提交：待提交

## 目标

在不把算法、前端或 Python Controller 绑定到 MuJoCo API 的前提下，为 Pegasus Iris 增加可运行
的四旋翼推力模型、统一控制入口和闭环控制所需的机体状态反馈。

## 主要改动

- 新增 Scene `properties.propulsion` 契约，描述二次推力模型、机体 Link、四个 Rotor Link、
  Actuator、局部推力轴、旋向、推力/反扭矩系数和转速范围。
- 新增严格的四旋翼参数解析与 Scene 验证：拒绝错误 Rotor 数量、悬空 Link/Actuator、重复资源、
  非法旋向、非有限参数和错误范围。
- MuJoCo Session 每个 physics step 按 `F = k_f * omega^2` 和
  `M_z = direction * k_m * omega^2` 计算世界坐标力/矩；各 Rotor 的推力、`r × F` 安装力矩和
  反扭矩汇总后统一作用于主刚体，避免 0.005 kg Rotor Link 被反扭矩加速至数千 rad/s 后造成
  数值发散。
- Iris robotics cache 增加 4 个 `velocity` Actuator，控制范围为 `0..1100 rad/s`；将未 authored
  而被 importer 临时设成 1 kg 的 Rotor Mass 改为 profile 明确声明的 0.005 kg。
- 修复 OpenUSD Joint 指向刚体内部子节点时的坐标系丢失：导入器现在会把 `localPos/localRot`
  从 authored target 重映射到实际 owning rigid-body frame。Iris 四个 Rotor 的 Link、Joint Origin
  和 Parent Frame 已同步更新，不再相对机身旋转 90° 后错位。
- `ControllerAction` 增加 `actuator_controls`，与 `position_targets` 同一事务验证和应用；
  `ControllerObservation.bodies` 增加位姿、世界坐标线速度和角速度。
- 新增通用 `setActuatorControls` Bridge 和
  `PUT /api/v1/simulations/{id}/actuator-controls` REST 接口。
- 新增 `QuadrotorAdapter`：将 Gymnasium 的 4 维归一化 Action 映射到 Rotor 转速，并输出 13 维
  Body Observation（Position、Quaternion、Linear Velocity、Angular Velocity）。
- gRPC/Backend State 增加 Body Linear/Angular Velocity，握手和 Schema Contract 升级为 v2，
  防止新旧状态布局静默混用。
- 前端 Inspector 新增四个 Rotor 转速控件和原子 `Stop Rotors` 操作。
- 新增可直接加载的 `examples/controllers/iris_hover.py`；根据当前 1.52 kg Iris 的实际质心、
  Rotor 安装点和旋向求得静态 Trim `[641.132, 679.039, 646.467, 673.963] rad/s`，并在 0.5 秒
  可视化预转后执行两秒平滑起飞，使用高度/垂直速度反馈在高一米处制动悬停。
- Three.js Viewport 根据仿真时间、Rotor Control 和旋向积分纯视觉旋翼相位；显示转速按比例降低
  以避免浏览器采样混叠，不参与物理计算。
- 修复浏览器保存场景中的项目级 `art_*` 引用跨项目失效：加载场景时按稳定 `asset_id` 将
  Actor 和 Robotics 内的资源字段重绑定到当前项目缓存，避免旧 Artifact ID 被误当成路径并触发
  `Imported asset path must be inside assets/imported`。

## 接口边界

| 使用方 | 控制入口 | 状态反馈 |
| --- | --- | --- |
| Web/人工调试 | REST/Bridge named actuator map | REST state + WebSocket |
| Python Controller | `ControllerAction.actuator_controls` | immutable body/joint/actuator observation |
| Gymnasium | `QuadrotorAdapter.command()` | 13 维 body observation |
| 远程算法 | 现有 dense gRPC `ControlCommand` | gRPC BackendState v2 |
| MuJoCo | stable actuator ID 映射 | 唯一负责 force/torque 和 engine index |

## 验证

- Iris 800 rad/s × 4 的真实 MuJoCo 烟测：100 steps 后机体相对初始高度上升超过 0.04 m，
  主刚体合力与四个 Rotor 的二次推力总和一致，Rotor Link 不再承受外部 Wrench。
- Iris Takeoff and Hover Controller 可由可信 Controller Loader 加载；真实 MuJoCo 从初始高度平滑
  爬升一米并在 6 秒内稳定，水平误差小于 `1e-4 m`，且无数值失稳。
- 真实 Chromium 跨端口验收覆盖 Iris 资产加载、Python 上传、Run、WebSocket 状态推进、起飞高度、
  Controller Active/Step Count 和 Rotor Control 反馈。
- 增加 Iris 源 USD 和缓存模型双重坐标回归，并由前端 `jointLocalPose` 真实读取缓存，确认四个
  Rotor 的零位姿与 Link Transform 完全一致。
- REST 真实资源流程：创建 Project、添加 Iris、创建 Simulation、写入 4 个 named controls、Step
  和状态返回全部通过。
- 本地 Gym `QuadrotorAdapter`、Body Velocity State 和远程 gRPC 序列化路径通过。
- Python 全量：250 passed、3 skipped；本轮坐标修复相关测试：38 passed；OpenUSD importer：
  12 passed。
- 前端模块测试：Store、Simulation、Trajectory、Kinematics、Geometry Bundle、Vite Runtime Config
  全部通过。
- TypeScript typecheck、Vite production build、Ruff 和 Mypy 通过。

## 已知限制

- 当前是静态二次推力模型，尚未包含 Motor Spool、Propeller Inflow、Body Drag、Wind、Ground
  Effect 和 Battery Sag。
- `iris_hover.py` 是针对当前 Iris Profile 的起飞与定高控制器，尚无水平位置和姿态闭环；改变
  质量、惯量、Rotor 安装点或施加水平/姿态扰动后仍需要完整飞控。
- v2 gRPC Client 需要配套 v2 Server；版本不一致会在 CreateSession 阶段明确拒绝。

## 下一步

- 基于 Body Position/Quaternion/Velocity 实现 Cascaded Attitude + Altitude Controller 和 Mixer。
- 增加 Motor First-order Dynamics、Aerodynamic Drag、Wind Disturbance 与 Ground Effect Profile。
- 为 Gymnasium 增加 Hover/Takeoff Task、随机化和 Episode Benchmark。
