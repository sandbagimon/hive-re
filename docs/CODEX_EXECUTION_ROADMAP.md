# SimLab Codex 开发交接与执行路线

更新日期：2026-07-15
适用仓库：`hive-re`（产品名：SimLab）  
状态：当前执行路线，优先级高于历史 iteration 文档；长期范围仍以 `PRODUCT_PLAN.md` 为准。

## 1. 给新环境 Codex 的任务说明

SimLab 当前已经完成一个可运行的基础闭环：TypeScript/three.js 编辑器可以导入 OpenUSD
可见网格、编辑 primitive/mesh actor、导出 MJCF，并在进程内运行 MuJoCo 后把刚体位姿同步回
viewport。下一阶段不要继续堆普通 UI 或 primitive，而要完成 **OpenUSD Physics/Articulation 导入到
可控 MuJoCo 运行时的垂直闭环**。

当前短期目标演示：

```text
通过 Import USD 从磁盘加载一个带固定基座、多个 Link、Joint 和 Drive 的外部 OpenUSD 机器人手臂资产
-> Scene Tree 保留 Robot/Link/Joint 层级
-> 导出并编译 MJCF
-> 固定步长运行 MuJoCo
-> UI 设置各关节的目标位置
-> actuator 在重力、惯性、关节限位和接触约束下驱动手臂
-> link/joint 状态同步到 viewport 和 inspector
-> 保存并重新打开后结构与行为一致
```

在该演示闭环完成前，不优先实现 ROS 2、强化学习、云服务、GPU 并行、照片级渲染或复杂
材质系统。

这里的“机器人手臂”必须来自用户选择的外部 `.usd`、`.usda`、`.usdc` 或 `.usdz` 文件。实现不得
在代码中内置机械臂几何、关节拓扑或特定 Prim 名称，也不得用程序生成 primitive 手臂代替产品验收。
程序生成的 USD 仅可用于隔离单元测试；端到端验收必须经过与用户导入相同的文件选择、依赖解析、
项目缓存和 Import Report 路径。

## 2. 当前已验证基线

截至 2026-07-14，本工作区验证结果：

- `python -m pytest -q`：34 passed，2 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- `npm run test:frontend`：EditorStore 测试通过。
- `npm run typecheck`：当前机器未找到 `tsc`，不能视为通过；先执行 `npm install`，再单独运行并
  检查退出码。

文档中的旧测试数量可能过期。每次交接应以当次实际命令结果为准，并更新 iteration log。

当前 OpenUSD importer 的真实边界：

- 支持 `.usd/.usda/.usdc/.usdz`。
- 读取 `UsdGeomMesh` points、face indices、stage units、up axis、层级 world transform 和第一组
  `displayColor`。
- 读取基础 rigid-body enabled/kinematic、mass/density、static/dynamic friction、restitution。
- 将所有 mesh 合并成一个 Actor，同时生成 `visual.json` 和 `collision.obj`。
- 不保留 Prim 层级，不读取 Joint、Articulation、Drive、独立 collider、inertia、sensor 或 actuator。

关键代码入口：

- `src/simlab/services/openusd_importer.py`
- `src/simlab/models/actor.py`
- `src/simlab/services/mjcf_exporter.py`
- `src/simlab/services/simulation_session.py`
- `src/simlab/services/simulation_service.py`
- `src/simlab/editor_bridge.py`
- `src/simlab/web_viewport/ts/`

## 3. 不可破坏的架构约束

1. **Clean-room**：不得复制 OrcaLab/OrcaSim 的代码、协议、素材、品牌、UI 文案或私有业务逻辑。
2. **统一中间模型**：USD/MJCF/URDF importer 不直接操作 MuJoCo，也不把未结构化 XML/USD
   字段整体塞进 `Actor.properties`。
3. **前后端职责**：TypeScript Editor Store 拥有 authoring scene、selection、history 和 dirty state；
   Python 接收不可变 snapshot，负责文件 IO、导入、验证、导出和 simulation runtime。
4. **状态分离**：authoring transform 不得被 simulation pose 覆盖；运行时状态使用单独的数据流。
5. **显式损失报告**：格式转换中任何默认、近似、降级或不支持字段都必须进入 Import Report，
   禁止静默丢弃。
6. **固定物理时钟**：物理步进、控制更新和 viewport 刷新必须解耦，不能长期依赖 Qt 16 ms UI
   timer 作为仿真时钟。
7. **小步提交**：每个任务必须带测试、文档/iteration 更新和明确验收证据；不要在一次修改中同时
   重写 importer、scene model、runtime 和整个 UI。

## 4. 目标数据模型

先在 `shared/schemas/robotics.schema.json` 定义版本化契约，再实现 Python dataclass 和 TypeScript
类型。至少包含：

```text
Articulation
+-- id / name / root_link_id
+-- links[]
|   +-- visual_geometries[]
|   +-- colliders[]
|   +-- mass / center_of_mass / inertia
+-- joints[]
|   +-- type / parent_link / child_link
|   +-- origin / axis / limits / initial_position
+-- actuators[]
|   +-- joint_id / control_type / control_range / gains
+-- sensors[]
```

模型要求：

- ID 稳定且不依赖显示名称。
- Link 使用局部 Transform，能够计算世界 Transform。
- Joint 第一版支持 `fixed`、`revolute`、`continuous`、`prismatic`。
- Collider 与 visual geometry 分离。
- Mass、center of mass、diagonal/full inertia 的缺省规则明确。
- Actuator 第一版支持 position、velocity、motor/torque 三种抽象。
- schema 带 `version`，加载旧 scene 时有迁移入口。

## 5. Gate 1A：OpenUSD Articulation 导入

### 1A.1 建立 fixture 和导入报告

先新增一个可再发行、许可证明确的外部 USD 机器人手臂 fixture。fixture 必须作为独立 USD 文件通过
公开导入入口加载，而不是由 importer 特判；程序化生成只允许用于补充单元测试。资产必须含：

- fixed base；
- 至少三个独立 link；
- 至少两个 revolute joints；
- collision prim；
- mass/inertia；
- position drive 或能够映射为 position actuator 的控制信息；
- 明确的 joint axis、limit 和 home position。

外部资产导入还必须验证相对 reference/payload、mesh 等依赖路径；首版无法支持的 composition 或
schema 必须写入 Import Report，不能依赖某个 fixture 的目录结构或 Prim 命名才能成功。

定义 `ImportIssue`：`severity`、`code`、`prim_path`、`field`、`message`、`fallback`。

验收：fixture 可由 OpenUSD 打开；导入失败能定位到 Prim/字段；第三方来源和许可证有记录。

### 1A.2 拆分 importer

将现有单体 importer 渐进拆分为：

```text
services/openusd/
+-- stage_loader.py
+-- geometry_importer.py
+-- physics_importer.py
+-- articulation_importer.py
+-- dependency_resolver.py
+-- import_report.py
```

保持当前单刚体导入 API 兼容，避免一次性破坏已有测试和资产。

### 1A.3 保留 Prim 层级和几何

- 建立 USD Prim Path 到 SimLab stable ID 的映射。
- 保留 Xform/Link 父子关系和 local transform。
- 每个 Link 保留各自 visual geometry，不再对 articulation 全局合并。
- 正确转换 meters-per-unit 和 Y-up/Z-up。
- 处理 active/visibility；instance/reference/payload 第一版允许报告为受限能力，但不得静默展开错误。

### 1A.4 导入 USD Physics

第一版支持：

- `UsdPhysics.ArticulationRootAPI`
- `UsdPhysics.RigidBodyAPI`
- `UsdPhysics.MassAPI`
- `UsdPhysics.CollisionAPI`
- Fixed/Revolute/Prismatic Joint
- Joint axis 和 limits
- `UsdPhysics.DriveAPI` 的 position/velocity target、stiffness、damping、max force 可表达子集

明确暂不支持项并报告，例如 spherical/distance joint、复杂 material network、动画和高级 schema。

Gate 1A 验收：从磁盘选择外部 fixture 后，能在序列化结果中看到独立 base/links、joint 连接、axis、
limit、home position、mass、inertia 和 collider；相关资产依赖被解析或明确报告；保存重开不丢字段；
更换合法 Prim 名称后仍可导入；旧单 Mesh USD 测试继续通过。

## 6. Gate 1B：MJCF 转换和运行时状态

### 1B.1 Articulation 到 MJCF

扩展 exporter：

| SimLab | MJCF |
|---|---|
| Articulation/Link | nested `<body>` |
| Joint | `<joint>` / `<freejoint>` |
| Collider | `<geom>` |
| Actuator | `<position>` / `<velocity>` / `<motor>` |
| Sensor | `<sensor>`（按已支持子集） |

必须有名称去重、相对 asset 路径、joint range、mass/inertia 和 actuator range 的验证。

### 1B.2 Runtime state bridge

扩展 `SimulationState`，至少提供：

- simulation time；
- 每个 Link 的 world pose；
- joint qpos/qvel；
- actuator ctrl/force（可获得时）；
- contact/diagnostic warnings。

前端 viewport 按 Link 更新 simulation transform，不回写 authoring transform。

### 1B.3 固定步长 simulation clock

将物理循环从 `EditorBridge.simulation_timer` 解耦。定义：

- physics timestep；
- control timestep；
- render publish rate；
- real-time factor；
- pause/step/reset 行为；
- catch-up 或 drop policy；
- shutdown 和异常传播。

要求 UI 不阻塞，并增加确定性的 N-step 测试和至少一个短时 soak test。

Gate 1B 验收：USD 机器人手臂可导出为 MuJoCo 可编译模型；step 后受控 joint 和对应 link pose
发生预期变化；重力、关节限位和 collider 在运行时生效；运行、暂停、单步、重置状态一致。

## 7. Gate 1C：机器人手臂关节控制闭环

### 1C.1 输入协议

TypeScript 维护关节目标状态，并按 stable joint ID 发送控制命令：

```json
{
  "mode": "joint_position",
  "targets": {"joint_shoulder": 0.35, "joint_elbow": -0.6}
}
```

要求：目标值使用弧度并受 joint limit 约束；未出现在命令中的关节保持最近目标；仿真停止、reset
或 bridge 断开时恢复安全 home target；禁止用显示名称作为运行时主键。

### 1C.2 JointPositionController

控制器与具体 UI 控件和 MuJoCo actuator 名称解耦。机器人配置声明 joint 到 actuator 的映射、home
position、控制范围、stiffness、damping 和最大力。第一版只实现关节空间 position control；velocity、
torque、末端位姿拖拽和 IK 在该闭环稳定后扩展。

### 1C.3 安全与体验

- control range 限幅；
- joint limit 和 actuator force 限制；
- 每个可控关节提供 slider、数值输入和当前 qpos/qvel 反馈；
- Home 恢复预设姿态，Reset 恢复完整仿真初态；
- bridge 断开或控制异常时冻结/回退到安全目标；
- 最小状态区显示 simulation state、time 和 controller fault。

Gate 1C 验收：用户可独立操作至少两个关节，关节在限位内跟随目标；link pose、qpos/qvel 和控制器
状态实时同步；手臂在重力和碰撞约束下稳定运行；Home/暂停/单步/Reset 行为一致；连续运行至少
10 分钟无 UI 卡死和明显时钟漂移。

## 8. Gate 2 及以后

Gate 1 完成后按以下顺序继续，详细范围见 `PRODUCT_PLAN.md` 和 `PLATFORM_GAP_MATRIX.md`：

1. **Gate 2：专业编辑和调试**：scene hierarchy 编辑、多选/复制、snap、typed inspector、独立
   Validation Panel、collision authoring、timeline、record/replay、project manifest、autosave recovery。
2. **Gate 3：传感器和任务平台**：joint/IMU/contact/force，基础 RGB/depth/segmentation，完整
   Gymnasium Env、headless batch、seed/determinism、domain randomization、dataset、ROS 2 基础 bridge。
3. **Gate 4：规模和高保真**：MJX/vectorized runtime 评估、GPU/多节点、USD round-trip 增强、
   合成数据和 SIL/HIL adapter。Gate 4 必须先定义 benchmark 和目标硬件。

MJCF importer 和 URDF importer 仍然需要，但在当前执行顺序中位于 USD 机器人手臂垂直闭环之后；两者
必须复用同一个 Robotics Intermediate Model，禁止各自建立不兼容的 scene 表示。

## 9. 每个 Codex 迭代的工作协议

开始任务前：

1. 阅读本文件、`README.md`、`PRODUCT_PLAN.md` 和相关最新 iteration。
2. 执行 `git status --short`，保留用户已有修改。
3. 运行与任务相关的最小基线测试。
4. 明确本轮只完成一个可验收子任务，不跨 Gate 扩张。

完成任务前：

```powershell
python -m pytest -q
python -m ruff check src tests
python -m mypy src
npm install
npm run typecheck
npm run test:frontend
```

涉及 Qt/WebEngine 的修改还要执行桌面 smoke test；涉及 MuJoCo/OpenUSD 的条件测试不得因依赖缺失
而被误报为通过，应记录 skipped 原因。

每轮必须：

- 新增或更新测试；
- 新增 `docs/iterations/YYYY-MM-DD-短标题.md`；
- 记录修改、验证、已知限制和下一步；
- 若 Gate 状态变化，同步更新本文件、`PRODUCT_PLAN.md` 和 `PLATFORM_GAP_MATRIX.md`；
- 不用“接口存在”代替端到端验收。

## 10. 第一项具体任务（已完成 2026-07-15）

第一项任务严格限定为：

> 定义版本化 Robotics Intermediate Model 和 `shared/schemas/robotics.schema.json`，覆盖
> Articulation、Link、Joint、Actuator、Sensor、VisualGeometry、Collider 和 Inertial；实现 Python
> dataclass、序列化/反序列化、schema validation、旧 Scene 兼容入口和单元测试。暂不修改 USD
> importer、MJCF exporter 或 UI。

第一项任务验收：

- Robotics JSON fixture 能表达 fixed base + three links + two revolute joints + two position actuators；
- JSON round-trip 相等；
- 重复 ID、悬空 parent/child、非法 axis/range、actuator 指向不存在 joint 会失败并定位字段；
- 原有 scene 和全部测试保持兼容；
- 文档记录下一项任务为外部 OpenUSD Prim/Physics 到该模型的通用映射。

实现证据见 `docs/iterations/2026-07-15-robotics-intermediate-model.md`。

## 11. Gate 1A.1（已完成 2026-07-15）

下一项任务严格限定为 Gate 1A.1：

> 建立 `ImportIssue`/`ImportReport` 和一个许可证明确、作为独立文件加载的最小外部 OpenUSD
> 机器人手臂 fixture；增加 stage loader 与依赖诊断，但暂不修改 MJCF exporter、runtime 或 UI。

验收：

- fixture 由公开 OpenUSD API 从磁盘打开，包含 fixed base、三个 link、两个 revolute joint、collision、
  mass/inertia 和 position drive；
- Import Report 可定位 Prim path、字段、严重级别、错误码和 fallback；
- 缺失 reference/payload/mesh 依赖被明确报告；
- importer 不依赖 fixture 的文件名、Prim 名称或固定拓扑；
- 原有单 Mesh USD 导入 API 和测试保持兼容。

实现证据见 `docs/iterations/2026-07-15-openusd-stage-loader.md`。

## 12. OpenUSD Articulation 映射（已完成 2026-07-15）

下一项任务限定为 Gate 1A.2/1A.3 的首个垂直子集：

> 新增通用 articulation importer，将外部 USD 中的 ArticulationRoot、RigidBody、Mass、Collision、
> Fixed/Revolute Joint 和 angular position Drive 映射到 RoboticsModel；保留 Prim path 与 stable ID，
> 不修改 MJCF exporter、runtime 或 UI。

验收：

- 外部机械臂 fixture 映射为 fixed base、三个 link、两个 revolute joint 和两个 position actuator；
- mass、center of mass、diagonal inertia、joint axis/limit、drive target/gain/max force 不丢失；
- visual geometry 与 collider 分离，并保留 local transform；
- stable ID 不依赖显示名称，合法改名后拓扑和引用仍正确；
- 不支持 schema 或近似转换进入 Import Report；现有单 Mesh importer 继续通过。

实现证据见 `docs/iterations/2026-07-15-openusd-articulation-mapping.md`。

## 13. Robot Project Import（已完成 2026-07-15）

> 将 articulation importer 接入项目资产缓存与正式 Import USD RPC：复制外部源文件和可解析依赖，
> 写入 `robotics.json`、manifest 和 Import Report，注册 `robot` asset，并让 Scene 保存/重开后保留
> RoboticsModel。暂不修改 MJCF exporter 和 simulation runtime。

验收：

- 通过现有 Import USD 入口选择外部机械臂时返回 `robot` asset，而不是合并为 object；
- 项目缓存包含源 USD、robotics model、manifest 和 import report，路径均为项目相对路径；
- 缺失 blocking dependency 不产生半成品 metadata；
- 保存 scene 后移动项目目录仍能重开机器人结构；
- 原有单 Mesh USD 导入结果和缓存格式保持兼容。

实现证据见 `docs/iterations/2026-07-15-openusd-robot-project-import.md`。

## 14. Robot Tree and Viewport（已完成 2026-07-15）

> 在 TypeScript Scene Tree 和 three.js viewport 中读取 Scene.robotics：展示 Robot/Link/Joint 层级，
> 按 Link local transform 渲染 primitive VisualGeometry，并保持 robot actor 的 authoring transform。
> 暂不接 MJCF/runtime，也不把 simulation pose 写回 authoring 数据。

验收：

- 导入外部 fixture 后 Scene Tree 展开显示 3 links 和 2 joints；
- viewport 显示 base、upper arm、forearm，层级变换与 USD/RoboticsModel 一致；
- robot actor translate/rotate/scale 作用于 articulation root；
- 选择 robot/link/joint 不破坏现有 actor selection、undo/redo 和 dirty state；
- 普通 primitive/mesh actor 渲染与编辑保持兼容。

实现证据见 `docs/iterations/2026-07-15-robot-tree-viewport.md`。

## 15. Articulation to MJCF（已完成 2026-07-15）

> 扩展 MJCF exporter，将 Scene.robotics 中的 Articulation/Link/Joint/Collider/Inertial/Actuator
> 转换为 nested body、joint、geom、inertial 和 actuator；外部机械臂必须能由 MuJoCo 编译。
> 暂不实现 runtime joint state bridge 和控制 UI。

验收：

- fixed-base articulation 生成嵌套 body，不额外创建 freejoint；
- revolute joint axis/range、初始 qpos、link mass/inertia 和 primitive collider 尺寸正确；
- position actuator 的 ctrlrange、kp 和 force range 正确；
- fixture 生成的 MJCF 可由 `mujoco.MjModel.from_xml_string()` 编译；
- primitive/object exporter 与现有 visual/physics fidelity 测试保持兼容。

实现证据见 `docs/iterations/2026-07-15-articulation-mjcf-export.md`。

## 16. Runtime Robotics State（Python 已完成 2026-07-15）

> 扩展 MuJoCo SimulationState 和 Bridge，发布每个 Link world pose、joint qpos/qvel 和 actuator ctrl；
> viewport 使用独立 simulation transform 更新 Link Group，停止/重置后恢复 authoring transform。

已完成：外部机械臂加载 home key、step 后状态包含稳定 Link/Joint/Actuator ID；运行时状态不修改
Scene.robotics；Reset 恢复 home；现有 actor pose sync 保持兼容。

实现证据见 `docs/iterations/2026-07-15-runtime-robotics-state.md`。

## 17. Runtime Link Viewport Sync（已完成 2026-07-15）

> 扩展 TypeScript SimulationState 和 viewport，消费 Link world pose、joint qpos/qvel 和 actuator ctrl；
> simulation transform 与 authoring transform 分离，停止/重置后恢复 Scene.robotics 姿态。

实现证据见 `docs/iterations/2026-07-15-runtime-link-viewport-sync.md`。

## 18. Joint Position Command RPC（已完成 2026-07-15）

> 新增 joint-position command RPC：按 stable joint ID 接收目标，映射到 position actuator ctrl，执行
> joint/actuator range 限幅；Session 不存在、非 position actuator 或未知 joint 时返回结构化错误。

验收：设置 shoulder/elbow target 后 MuJoCo ctrl 更新，step 后 qpos 朝目标运动；越界目标被限幅；
Reset 恢复 home target；命令不修改 Scene.robotics authoring 数据。

实现证据见 `docs/iterations/2026-07-15-joint-position-command.md`。

## 19. Joint Control UI（已完成 2026-07-15）

> 在 robot Property Panel 增加每个 position joint 的 slider、目标数值、qpos/qvel 反馈和 Home；目标
> 通过 setJointTargets RPC 发送，只有 simulation state 改变，不写 authoring joint initial_position。

验收：用户可独立控制 shoulder/elbow，UI 范围来自 joint/actuator limit，状态反馈实时更新；Home
恢复目标，Run/Pause/Step/Reset 与控制一致。

实现证据见 `docs/iterations/2026-07-15-joint-control-ui.md`。

## 20. External Robot Gate 1 Physics Workflow（已完成 2026-07-15）

> 从外部 USD 文件开始，完成缓存、scene 保存重开、preflight、MJCF 编译、shoulder/elbow target、
> 持续 step、link pose、限位和 Reset home 的自动化验收。

验收同时修复三项阻断机械臂运动的 MJCF 契约：显式声明弧度单位、排除直接相连 Link 的碰撞、
传递 USD drive damping。实现证据见 `docs/iterations/2026-07-15-external-robot-gate.md`。

## 21. Controller Safety State（已完成 2026-07-15）

> 补充 controller command 原子更新和 timeout/fault 状态；验证异常命令不留下部分 ctrl 更新，
> 启用 watchdog 后控制输入中断会恢复 Home target。

SimulationState 现包含 controller status/message/command_time/timeout，Joint Control UI 会显示明确状态。
`simulation_config.control_timeout` 默认关闭，设置正数后按仿真时间启用 watchdog。

实现证据见 `docs/iterations/2026-07-15-controller-safety.md`。

## 22. External Robot Control Soak（已完成 2026-07-15）

> 外部机械臂持续执行 40 轮交替 target、累计 2,000 个 MuJoCo step，逐段检查 time、qpos/qvel、
> Link pose、actuator ctrl/force 全部有限且不越限，并输出带 cycle 和 stable ID 的 failure context。

实现证据见 `docs/iterations/2026-07-15-robot-control-soak.md`。

## 23. Fixed Physics Clock（已完成 2026-07-15）

> QTimer callback 与 MuJoCo timestep 已解耦；SimulationService 使用 monotonic elapsed-time
> accumulator 计算固定物理步数，并通过 `max_catch_up_steps` 限制单帧补算。

Pause/Resume 会清空墙钟间隙，callback 不足一个 timestep 时只发布当前状态，不提前推进。实现证据见
`docs/iterations/2026-07-15-fixed-physics-clock.md`。

## 24. Runtime Fault Containment（已完成 2026-07-15）

> MuJoCo step 异常和非有限状态会停止 SimulationService clock 与 QTimer，保留最后有效画面，
> 切换 simulation badge 到 Fault，并在 Console 发布带 stable ID 的错误。

实现证据见 `docs/iterations/2026-07-15-runtime-fault-containment.md`。

## 25. Robot Reset/Home State Sync（已完成 2026-07-15）

> Reset 现在保留已编译 session，返回并发布 Home runtime state，切换为 Paused；viewport、joint
> feedback 和 controller badge 在同一操作中恢复。Stop 独立用于场景失效、切换和关闭。

实现证据见 `docs/iterations/2026-07-15-robot-reset-state-sync.md`。

## 26. Path-Based Robot Bridge Workflow（已完成 2026-07-15）

> `importOpenUsdPath` 提供无需原生文件对话框的可测试导入边界；完整 Bridge workflow 已覆盖外部
> 路径导入、actor 创建、Run、Joint target、fixed-clock frame、Pause 和 Reset。

原有 Import USD 按钮继续使用文件对话框，但选择路径后复用相同 RPC 实现。实现证据见
`docs/iterations/2026-07-15-robot-bridge-workflow.md`。

## 27. Live Joint Feedback and Jog（已完成 2026-07-15）

> Joint Control 提供可配置 step size、每关节减/增 Jog、range 和数值输入；所有路径复用
> setJointTargets。qpos/qvel/ctrl/controller 通过局部 DOM 更新实时刷新，不重建 Inspector。

输入获得焦点时 runtime ctrl 不覆盖正在编辑的值；range/number 的原生方向键使用配置后的 step。
实现证据见 `docs/iterations/2026-07-15-live-joint-jog.md`。

## 28. Robot Joint Selection（已完成 2026-07-16）

> Scene Tree joint 可选择且不影响 dirty/history；Property Panel 聚焦当前 joint 的 topology、axis、range、
> live state 和控制，viewport 高亮并 outline child Link。选择 robot actor 仍显示全部 joint 总览。

Frame Selected 会使用 child Link bounds，Store 拒绝不属于 actor 的 joint ID。实现证据见
`docs/iterations/2026-07-16-robot-joint-selection.md`。

## 29. Editor Automation and Qt Robot UI E2E（已完成 2026-07-16）

> 受控 Editor Automation API 支持按 path 导入 USD、读取 JSON state 和选择有效 joint；真实
> QtWebEngine offscreen 测试验证 robot tree、Joint Inspector、Jog、canvas 和非空截图。

MainWindow 支持注入临时 project root，视觉测试不会污染仓库资产。显式视觉门禁通过并生成
`/tmp/simlab-robot-joint-ui.png`。实现证据见 `docs/iterations/2026-07-16-qt-robot-ui-e2e.md`。

## 30. Qt Robot Run/Jog/Pause/Reset E2E（已完成 2026-07-16）

> 真实 Qt 页面通过 Run、Jog、Pause、Reset 完成机械臂控制闭环；自动验证 qpos、child Link
> quaternion、live Inspector、暂停时间冻结和 Reset Home，运行态截图非空。

运行中 Jog 现在保持 Running status。Preflight 将有效 robot articulation 计为 physics actor，并拒绝
悬空 articulation reference，不再误报 `NO_PHYSICS_ACTORS`。实现证据见
`docs/iterations/2026-07-16-qt-robot-control-e2e.md`。

## 31. Joint Trajectory Contract and Player（已完成 2026-07-16）

> Joint Trajectory schema 使用严格递增时间戳和 stable joint target map；纯 Python 播放器支持
> Play/Pause/Stop/Complete/Loop 和线性插值，时间源为 simulation time。

实现证据见 `docs/iterations/2026-07-16-joint-trajectory-contract.md`。

## 32. MuJoCo Trajectory Runtime and RPC（已完成 2026-07-16）

> JointTrajectoryPlayer 已接入 MuJoCo Session，每个 physics step 前更新 position targets；
> SimulationState 发布 trajectory，Bridge 提供 load/play/pause/stop RPC 和自然完成停表。

实现证据见 `docs/iterations/2026-07-16-mujoco-trajectory-runtime.md`。

## 33. TypeScript Trajectory Panel（已完成 2026-07-16）

> 实现 TypeScript Trajectory Panel：从当前 robot Home 与编辑目标生成最小轨迹，显示名称、状态、
> cursor/duration 和进度条，提供 Load、Play、Pause、Stop；runtime 更新使用局部 DOM，避免整页重绘。

真实 QtWebEngine 验收确认 panel、Joint Inspector 与 viewport 在 1360x860 窗口内无重叠，且原有
Run/Jog/Pause/Reset 闭环保持通过。实现证据见
`docs/iterations/2026-07-16-trajectory-panel.md`。

## 34. Trajectory Qt E2E（已完成 2026-07-16）

> 增加 Trajectory Qt E2E：从 UI 生成并加载外部 USD 机械臂轨迹，验证 Play 自然完成、Pause
> cursor 冻结、Stop 回到首帧，以及 simulation status、关节反馈和 viewport pose 同步。

真实 Qt 页面已覆盖 Home 到目标的 0.8 秒轨迹：中途 Pause 后 simulation/trajectory time 均冻结，
Stop 恢复首帧 target，重播自然完成后停表并同步最终 Link pose。实现证据见
`docs/iterations/2026-07-16-trajectory-qt-e2e.md`。

## 35. 当前下一项具体任务

> 实现可编辑 Keyframe List：显示关键帧时间和各关节 target，支持从当前关节状态捕获、修改时间、
> 删除与排序；所有编辑保存在前端 draft，Load 前通过共享 trajectory schema 校验。
