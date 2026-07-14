# SimLab Codex 开发交接与执行路线

更新日期：2026-07-14  
适用仓库：`hive-re`（产品名：SimLab）  
状态：当前执行路线，优先级高于历史 iteration 文档；长期范围仍以 `PRODUCT_PLAN.md` 为准。

## 1. 给新环境 Codex 的任务说明

SimLab 当前已经完成一个可运行的基础闭环：TypeScript/three.js 编辑器可以导入 OpenUSD
可见网格、编辑 primitive/mesh actor、导出 MJCF，并在进程内运行 MuJoCo 后把刚体位姿同步回
viewport。下一阶段不要继续堆普通 UI 或 primitive，而要完成 **OpenUSD Physics/Articulation 导入到
可控 MuJoCo 运行时的垂直闭环**。

目标演示：

```text
导入一个带底盘、车轮、Joint 和 Drive 的 OpenUSD 小车
-> Scene Tree 保留 Vehicle/Link/Joint 层级
-> 导出并编译 MJCF
-> 固定步长运行 MuJoCo
-> WASD 产生车辆控制命令
-> actuator 驱动车轮和转向
-> link/joint 状态同步到 viewport 和 inspector
-> 保存并重新打开后结构与行为一致
```

在该演示闭环完成前，不优先实现 ROS 2、强化学习、云服务、GPU 并行、照片级渲染或复杂
材质系统。

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

先新增一个可再发行、许可证明确的最小 USD 小车 fixture；也可在测试中程序化生成。它必须含：

- chassis rigid body；
- 至少两个 wheel rigid bodies；
- revolute wheel joints；
- collision prim；
- mass/inertia；
- drive 或能够映射为 actuator 的控制信息。

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

Gate 1A 验收：导入 fixture 后能在序列化结果中看到独立 chassis/wheels、joint 连接、axis、limit、
mass 和 collider；保存重开不丢字段；旧单 Mesh USD 测试继续通过。

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

Gate 1B 验收：USD 小车可导出为 MuJoCo 可编译模型；step 后 wheel joint 和 link pose 发生预期变化；
运行、暂停、单步、重置状态一致。

## 7. Gate 1C：WASD 车辆控制闭环

### 1C.1 输入协议

TypeScript 维护 pressed-key state，并发送归一化命令：

```json
{"throttle": 1.0, "steering": -1.0, "brake": 0.0}
```

要求：支持组合键；输入框聚焦时禁用；window blur、仿真停止或 bridge 断开时命令立即归零；禁止
依赖 key repeat 累加。

### 1C.2 VehicleController

控制器与具体按键、actuator 名称解耦。车辆配置声明 drive/steering actuators、最大速度、最大转向角、
制动力和回正速度。第一版可使用简化差速或双驱模型；若 fixture 具备转向 joint，再实现 Ackermann
映射。

### 1C.3 安全与体验

- control range 限幅；
- 命令超时自动清零；
- Space 制动、R 重置；
- 跟随相机；
- 最小 HUD：速度、throttle、steering、simulation state。

Gate 1C 验收：W 前进，S 制动/倒车，W+A/W+D 联合转向，松键回正，失焦停车，R 重置；连续
运行至少 10 分钟无 UI 卡死和明显时钟漂移。

## 8. Gate 2 及以后

Gate 1 完成后按以下顺序继续，详细范围见 `PRODUCT_PLAN.md` 和 `PLATFORM_GAP_MATRIX.md`：

1. **Gate 2：专业编辑和调试**：scene hierarchy 编辑、多选/复制、snap、typed inspector、独立
   Validation Panel、collision authoring、timeline、record/replay、project manifest、autosave recovery。
2. **Gate 3：传感器和任务平台**：joint/IMU/contact/force，基础 RGB/depth/segmentation，完整
   Gymnasium Env、headless batch、seed/determinism、domain randomization、dataset、ROS 2 基础 bridge。
3. **Gate 4：规模和高保真**：MJX/vectorized runtime 评估、GPU/多节点、USD round-trip 增强、
   合成数据和 SIL/HIL adapter。Gate 4 必须先定义 benchmark 和目标硬件。

MJCF importer 和 URDF importer 仍然需要，但在当前执行顺序中位于 USD 小车垂直闭环之后；两者
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

## 10. 新环境的第一项具体任务

第一项任务严格限定为：

> 定义版本化 Robotics Intermediate Model 和 `shared/schemas/robotics.schema.json`，覆盖
> Articulation、Link、Joint、Actuator、Sensor、VisualGeometry、Collider 和 Inertial；实现 Python
> dataclass、序列化/反序列化、schema validation、旧 Scene 兼容入口和单元测试。暂不修改 USD
> importer、MJCF exporter 或 UI。

第一项任务验收：

- fixture 能表达 chassis + two wheels + two revolute joints + two actuators；
- JSON round-trip 相等；
- 重复 ID、悬空 parent/child、非法 axis/range、actuator 指向不存在 joint 会失败并定位字段；
- 原有 scene 和全部测试保持兼容；
- 文档记录下一项任务为 OpenUSD Prim/Physics 到该模型的映射。

