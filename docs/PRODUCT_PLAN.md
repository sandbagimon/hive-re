# SimLab Product Plan

日期：2026-07-09
状态：长期路线图
最近评审：2026-07-10

> **当前执行顺序（2026-07-15）**：长期里程碑仍由本文定义；具体开发交接、任务切分和验收顺序
> 以 [`CODEX_EXECUTION_ROADMAP.md`](CODEX_EXECUTION_ROADMAP.md) 为准。当前先完成 OpenUSD
> Physics/Articulation 外部机器人手臂资产的端到端垂直闭环，再复用统一 Robotics Intermediate Model 扩展 MJCF、
> URDF 导入。

## 产品目标

SimLab 的目标是做一个本地优先的机器人仿真编辑器。产品能力对标现代机器人仿真工作台，但所有实现都必须是 clean-room 的：独立品牌、独立 UI、独立资产、独立数据结构、独立业务逻辑，不复制任何 OrcaLab 的代码、素材、云服务、包名、协议、文案或视觉表达。

核心技术路线：

- 物理仿真：MuJoCo。
- 桌面壳：PySide6。
- 3D viewport 和交互控制：本地 vendored three.js。
- 场景源格式：`scene.json`。
- 物理导出格式：MJCF。
- 自动化验证：pytest、ruff，后续增加 mypy 和端到端 UI smoke tests。

模块级现状、竞品公开能力、差距优先级和验收 Gate 统一记录在
[`PLATFORM_GAP_MATRIX.md`](PLATFORM_GAP_MATRIX.md)。本文件负责产品里程碑，差距矩阵负责逐模块追踪；两者在 milestone 完成时同步更新。

## 非侵权边界

必须遵守：

- 不使用 OrcaLab 名称、Logo、图标、截图、素材、示例项目或品牌元素。
- 不反编译、不抓取、不复制 OrcaLab 客户端或服务端代码。
- 不复制 OrcaLab 的私有协议、云服务接口、商业逻辑或包名。
- 不照抄 UI 布局、颜色系统、文案、动效和交互细节。
- 可以做功能等价：场景编辑、仿真运行、机器人导入、控制器、数据记录、批量实验、训练环境。
- 功能等价必须通过我们自己的架构、命名、视觉设计和交互设计实现。
- 每次引入第三方开源组件，都要记录许可证、来源、用途和替代方案。

## 当前已经实现

### 项目基础

- 已创建 Python `src/` layout 项目。
- 已配置 `pyproject.toml`。
- 已配置 `requirements.txt`，可在新机器上直接创建 `.venv` 后安装。
- 已添加 README、LICENSE、`.gitignore`。
- 已建立 Git 仓库和多次迭代提交。
- 已新增 `docs/iterations/`，用于记录每次迭代。

### 桌面应用

- 支持通过以下命令启动：

```powershell
python -m simlab.app
```

- 主窗口已有：
  - Top toolbar。
  - Asset Browser。
  - Scene Tree。
  - three.js Viewport。
  - Property Panel。
  - Console Panel。

### 场景模型

- 已实现：
  - `Transform`
  - `Actor`
  - `Scene`
- 支持 `scene.json` 序列化和反序列化。
- Actor 已包含：
  - `id`
  - `name`
  - `type`
  - `asset_id`
  - `transform`
  - `properties`
- Scene 已包含：
  - `version`
  - `name`
  - `units`
  - `actors`
  - `simulation_config`

### 项目和场景服务

- 已实现 `save_scene()` 和 `load_scene()`。
- 已实现基础验证：
  - scene version 存在。
  - actor id 唯一。
  - transform 向量长度为 3。
- 已实现 `SceneService`：
  - `new_scene()`
  - `add_actor()`
  - `remove_actor()`
  - `rename_actor()`
  - `update_transform()`
  - `update_actor_properties()`
  - `get_actor()`
  - `list_actors()`
- Actor id 已按 `actor_001` 形式生成。

### 资产系统初版

- 已添加本地 primitive assets：
  - Box
  - Sphere
  - Cylinder
  - Ground
  - Table
  - Ramp
- Asset Browser 可读取 `assets/metadata.json`。
- 双击资产或点击按钮可添加 actor 到场景。
- Dynamic primitive 默认带 mass/friction。
- Ground/Table/Ramp 默认是 static physics actor。
- 可从 UI 导入 `.usd`、`.usda`、`.usdc`、`.usdz` OpenUSD 资产。
- 导入器生成项目内 viewport/collision mesh cache，并注册到 Asset Browser。
- 支持从 UsdPhysics 读取基础 rigid-body、mass/density 和 friction 属性。
- OpenUSD mesh actor 可编辑物理属性、导出 MJCF 并由 MuJoCo 运行。

### three.js viewport 初版

- 已用 `QWebEngineView` 加载本地 HTML/JS/CSS。
- 编辑器前端已迁移为 TypeScript ES modules。
- Asset Browser、Scene Tree、Property Inspector、Console 已迁移到 TypeScript。
- TypeScript Editor Store 已接管 scene、selection、dirty、undo/redo。
- Python 与前端通过结构化 QWebChannel JSON RPC 通信。
- `MainWindow` 已缩减为单个 QWebEngineView 容器。
- 已 vendored three.js r160。
- 已保留 three.js MIT license 文件。
- Viewport 当前支持：
  - 显示 grid 和 axes。
  - 渲染 box/sphere/cylinder。
  - orbit camera。
  - 点击 mesh 选择 actor。
  - 选择状态同步到 Scene Tree 和 Property Panel。
  - translate gizmo。
  - 拖动后把 position 回写到 Python scene model。
  - Collider Debug Overlay：dynamic/static wireframe、质心和状态图例。

### MJCF 和 MuJoCo

- 已实现 MJCF exporter。
- 支持 primitive object actor：
  - box -> `<geom type="box">`
  - sphere -> `<geom type="sphere">`
  - cylinder -> `<geom type="cylinder">`
  - plane -> `<geom type="plane">`
- 支持 basic static/dynamic physics export：
  - dynamic actor -> body + freejoint + geom。
  - static actor -> fixed world geom。
  - mass/friction 可导出。
- Primitive geometry contract 已统一：
  - Box half extents、Sphere radius、Cylinder radius/half-height。
  - three.js XYZ radians 转 MuJoCo quaternion。
  - scale 烘焙到 collider size。
  - 非均匀 Sphere 转 Ellipsoid；Cylinder 要求 X/Y 等比缩放。
  - exporter 不再生成隐藏 ground。
- 已支持 Default/Rubber/Wood/Metal/Ice physics materials。
- 已支持 explicit mass 和 material density 两种质量模式。
- material preset 联动 friction、solref/solimp、roughness/metalness。
- 已保留 headless MuJoCo runner，可用于命令行 smoke run。
- UI 可导出 MJCF 并启动 in-process MuJoCo session。
- Console Panel 可显示 simulation event。
- 已实现 in-process MuJoCo simulation session。
- 已实现 Run/Pause/Step/Reset 基础控制。
- 已实现 MuJoCo body pose 到 three.js viewport 的实时同步。
- Simulation pose 会覆盖 viewport 显示，但不写回 authoring transform。
- Run/Step/Export 前执行 physics validation preflight：
  - 校验 dynamic/static、mass、friction 和 primitive 类型。
  - 使用 MuJoCo 编译生成的 MJCF。
  - UI 和 Console 显示带 actor/field 定位的错误。

### 测试

- 已有 pytest 覆盖：
  - scene model。
  - actor add/remove/update。
  - scene save/load。
  - scene history dirty/undo/redo。
  - asset metadata physics playground assets。
  - MJCF export。
  - MuJoCo model load。
  - MuJoCo simulation state sync。
  - OpenUSD mesh import、单位/坐标转换和 MuJoCo compile。
  - web viewport asset 文件存在性。
- 当前验证状态：
  - `pytest`：36 passed，1 skipped（MuJoCo 条件跳过）。
  - TypeScript typecheck：passed。
  - EditorStore Node test：passed。
  - `ruff`：passed。

## 总体架构目标

长期目标架构：

```text
SimLab Desktop
+-- PySide6 Application Shell
|   +-- QWebEngine container
|   +-- QtWebChannel JSON RPC bridge
|
+-- TypeScript Editor
|   +-- Editor Store / History / Selection
|   +-- Asset Browser / Scene Tree / Inspector
|   +-- Simulation Controls / Console / Diagnostics
|   +-- three.js Viewport
|
+-- Scene Core
|   +-- scene.json
|   +-- asset metadata
|   +-- actor graph
|   +-- transform hierarchy
|   +-- validation
|
+-- Simulation Core
|   +-- MJCF exporter
|   +-- MuJoCo model manager
|   +-- stepping loop
|   +-- state recorder
|   +-- reset / replay / pause
|
+-- Robotics Layer
|   +-- robot importer
|   +-- joints / actuators / sensors
|   +-- controller API
|   +-- task definitions
|
+-- Experiment Layer
|   +-- scripted runs
|   +-- batch evaluation
|   +-- metrics
|   +-- dataset export
|
+-- Packaging
    +-- local desktop distribution
    +-- reproducible examples
    +-- license notices
```

## Milestones

### M0 - Simulation-First MVP Foundation

状态：已完成。

目标：

- 建立可运行桌面项目。
- 建立 scene model。
- 支持 scene JSON save/load。
- 支持 primitive asset add。
- 支持 MJCF export。
- 支持 headless MuJoCo runner。

已完成内容：

- PySide6 desktop shell。
- Scene/Actor/Transform model。
- ProjectService 和 SceneService。
- Asset Browser、Scene Tree、Property Panel、Console。
- Primitive assets。
- MJCF exporter。
- MuJoCo runner。
- pytest/ruff。

验收标准：

- `python -m simlab.app` 可打开 UI。
- 可添加 primitive actors。
- 可保存和打开 `scene.json`。
- 可导出 `exports/scene.xml`。
- 可运行 headless MuJoCo runner。
- 测试通过。

### M1 - Local three.js Viewport

状态：第一版已完成，仍需增强。

目标：

- 用不依赖云服务的开源 3D viewport 替代 placeholder。
- 建立 Python 和 JavaScript 的双向同步。
- 支持基础 3D 编辑闭环。

已完成内容：

- QtWebEngine + three.js viewport。
- Primitive actor 渲染。
- Click selection。
- Orbit camera。
- Translate gizmo。
- Rotate gizmo。
- Scale gizmo。
- Selection outline。
- Transform mode toolbar。
- Frame selected。
- Front/right/top/isometric camera shortcuts。
- Position 回写 scene model。

剩余任务：

- 添加 snap to grid。
- 增加 viewport 坐标轴、网格尺寸和背景设置。
- 增加更完整的 viewport JS 单元或集成测试策略。

验收标准：

- 任何 scene model 变化都能反映到 viewport。
- 任何 viewport transform 编辑都能回写 scene model。
- 选中状态在 viewport、Scene Tree、Property Panel 之间一致。

### M2 - Robust Scene Editing Workflow

状态：基础可靠性已完成，增强项待做。

目标：

- 让场景编辑从 demo 状态进入可持续使用状态。

已完成：

- Dirty state。
- New/Open/Close 前未保存改动提示。
- Save 成功后清除 dirty。
- Undo/redo stack。
- `Ctrl+Z` / `Ctrl+Shift+Z` 快捷键。
- Toolbar Undo/Redo action。

剩余任务：

- Actor hierarchy。
- Parent/child transform。
- Duplicate actor。
- Multi-select。
- Auto-save recovery。
- Scene validation panel。
- Actor search/filter。
- Property Panel 支持 typed properties。
- Scene Tree context menu。
- Rename inline edit。
- Delete confirmation。
- Save/open 最近项目列表。

验收标准：

- 常规编辑操作可撤销和重做。
- 保存前可知道 scene 是否有未保存改动。
- 错误 scene 可被明确提示而不是静默失败。

### M3 - MuJoCo Live State Sync

状态：第一版已完成，仍需增强。

目标：

- 让 MuJoCo 不只是 headless 子进程日志，而是成为 viewport 的实时物理数据源。

已完成：

- In-process MuJoCo simulation manager。
- 将 scene export 为 MJCF 后加载到 `MjModel`。
- 管理 `MjData`。
- 支持 Run/Pause/Step/Reset。
- 每帧读取 body pose。
- 将 pose 推送到 three.js viewport。
- 基础区分 authoring transform 和 simulation transform。
- Console 显示基础 simulation event。

剩余任务：

- 更完整的 simulation overlay。
- 更清晰的 running/paused/reset UI 状态。
- 固定步长、real-time factor、长时间运行和速度控制。
- 与 UI timer 解耦的非阻塞 stepping 策略。
- 更完整的 warning/error report。

验收标准：

- 点击 Run 后 viewport 中 actor 随 MuJoCo step 实时更新。
- Reset 后 scene 恢复到 authoring 状态。
- 不阻塞 UI 主线程。

### M4 - Robot Import and Robotics Model

状态：进行中。

目标：

- 支持真实机器人模型，而不只是 primitive objects。

已完成：

- Robot/Link/Joint/Actuator/Sensor 共享 schema。
- VisualGeometry/Collider/Inertial 共享模型。
- Python dataclass、JSON round-trip 和语义校验。
- 旧 Scene 可选 `robotics` 字段兼容入口。
- OpenUSD stage loader、结构化 Import Report 和依赖诊断。
- 可再发行的外部 USD 双关节机械臂测试资产。
- OpenUSD ArticulationRoot/RigidBody/Mass/Collision/Joint/Drive 到 RoboticsModel 的通用映射。
- stage units、Y-up/Z-up、关节角度与惯量单位转换。
- 正式 Import USD robot asset、项目相对缓存、manifest/report 和 Scene robotics 持久化。
- TypeScript Scene Tree 的 Robot/Link/Joint 展示和 three.js 逐 Link primitive visual 渲染。
- Articulation/Link/Joint/Collider/Inertial/Actuator 到可编译 MJCF 的转换和 home keyframe。
- MuJoCo Link world pose、Joint qpos/qvel、Actuator ctrl/force runtime state。
- viewport 使用独立 simulation transform 同步 Link world pose，停止后恢复 authoring pose。

要实现：

- 外部 OpenUSD articulation、rigid body、joint 和 drive 映射。
- Robot actor type。
- Import MJCF。
- Import URDF。
- Mesh asset reference。
- Mesh/include/default/compiler 依赖解析。
- Joint model。
- Actuator model。
- Sensor model。
- Articulation runtime state bridge。
- Robot tree inspector。
- Initial pose editor。
- Joint limit validation。
- Robot asset metadata。

验收标准：

- 可从磁盘导入一个外部 OpenUSD 机器人手臂资产。
- 可在 viewport 中查看机器人结构。
- 可在 Property Panel 中查看 joints、actuators、sensors。
- 可导出可加载的 MJCF。

### M5 - Physics Authoring

状态：部分开始。

目标：

- 让用户能编辑 MuJoCo 关键物理参数。

已完成：

- Ground/Table/Ramp static primitive assets。
- Primitive actor 支持 basic `physics.dynamic`。
- Primitive actor 支持 basic mass/friction。
- Property Panel 可编辑 Dynamic、Mass、Friction。
- MJCF exporter 区分 dynamic/static primitive。
- Demo scene 已更新为 Physics Playground。
- Primitive geometry/transform/scale contract。
- Collider Debug Overlay。
- Default/Rubber/Wood/Metal/Ice material presets。
- Mass/density mode 和 contact/visual material mapping。
- Viewport/Python/MuJoCo geometry fidelity tests。
- Ramp -> Ground 可见接触轨迹测试。

剩余任务：

- Mass/inertia editor 扩展。
- Friction/contact parameters 扩展。
- Solver settings。
- Timestep and integrator settings。
- Collision groups。
- Constraints。
- Tendons。
- Equality constraints。
- World gravity。
- Terrain 和 heightfield authoring。

验收标准：

- 用户可从 UI 修改物理参数。
- 导出 MJCF 后参数保真。
- 错误或不稳定参数能被 validation 捕获。

### M6 - Timeline, Playback, and Recording

状态：未开始。

目标：

- 支持仿真控制、回放和数据记录。

要实现：

- Timeline widget。
- Play/pause/step/reset。
- Simulation speed control。
- Frame capture。
- State recording。
- Replay saved trajectory。
- Trajectory manifest 和仿真配置快照。
- Seed、版本指纹和确定性 replay 校验。
- Export CSV/JSON trajectory。
- Record selected body/joint/sensor data。

验收标准：

- 可录制一次仿真并回放。
- 可导出关键状态数据。
- UI 能显示当前 simulation time/frame。

### M7 - Asset Pipeline

状态：OpenUSD mesh 第一版已完成，资产管线仍需增强。

目标：

- 建立本地资产库和导入流程。

已完成：

- OpenUSD `.usd/.usda/.usdc/.usdz` 导入入口。
- Stage transform、单位和 up-axis 转换。
- `UsdGeomMesh` 三角化与项目内 visual/collision cache。
- Imported asset metadata 注册。
- 基础 UsdPhysics 属性导入。
- OpenUSD mesh -> MJCF -> MuJoCo 闭环。

剩余任务：

- Local asset library。
- Asset metadata schema。
- Mesh import。
- Texture/material import。
- Asset thumbnails。
- Asset validation。
- Asset dependency copying。
- Project-relative asset paths。
- Project manifest。
- Mesh collider 和碰撞近似流程。
- Example asset packs。

验收标准：

- 新资产可导入、预览、添加到场景。
- 项目移动目录后 asset 引用仍然可用。
- 许可证信息可记录到 asset metadata。

### M8 - Controller and Scripting API

状态：未开始。

目标：

- 让用户可以写控制器和自动化脚本。

要实现：

- Python controller interface。
- Per-step callback。
- Reset callback。
- Observation/action API。
- Controller attach UI。
- Script validation。
- Safe execution boundary。
- Transport-neutral controller boundary。
- ROS 2 adapter boundary。
- Built-in examples：
  - position controller。
  - velocity controller。
  - simple PID。

验收标准：

- 用户能把 Python controller 绑定到 robot。
- 仿真时 controller 能读取 sensor/joint state 并输出 actuator commands。
- Controller exception 不会崩掉整个 UI。

### M9 - Experiment and Gym-Style Environment

状态：stub 已存在，功能未开始。

目标：

- 支持批量实验、训练、评估和自动化运行。

要实现：

- 完整 `SimLabEnv`。
- `reset()` / `step()` / `close()` 语义。
- Observation spec。
- Action spec。
- Reward hooks。
- Termination hooks。
- Batch runner。
- Metrics collector。
- Seed control。
- Headless mode。
- Domain randomization hooks 和 episode 参数记录。
- Vectorization boundary。
- External RL library adapter。

验收标准：

- 可用 Python 脚本 headless 运行 task。
- 可重复 seed。
- 可导出 metrics。
- 不强制依赖 gymnasium，但可提供 adapter。

### M10 - Diagnostics, Validation, and Test Coverage

状态：部分开始。

目标：

- 提升产品稳定性，避免 scene、MJCF、viewport、MuJoCo 状态不一致。

要实现：

- Scene schema versioning。
- Migration system。
- Validation report panel。
- MJCF load check。
- Asset dependency check。
- UI smoke tests。
- Viewport bridge tests。
- Simulation regression tests。
- Performance budget tests。
- Actor/geom scaling benchmarks 和 soak tests。
- Crash-safe logging。
- Crash bundle。

验收标准：

- 错误 scene 能给出明确定位。
- 导出 MJCF 前后可自动验证。
- CI 可以在无 GUI 环境中跑核心测试。

### M11 - Packaging and Distribution

状态：未开始。

目标：

- 把开发环境变成可交付桌面应用。

要实现：

- Windows packaging。
- Application icon and original branding。
- License notices。
- Example projects。
- First-run sample scene。
- Crash log location。
- Version info。
- Release checklist。
- Optional installer。

验收标准：

- 非开发机器可安装运行。
- 不需要用户手动配置 Python 环境。
- 第三方 license notice 完整。

### M12 - Product Polish and Workflow Parity

状态：未开始。

目标：

- 让 SimLab 成为完整工作台，而不是功能拼装 demo。

要实现：

- 独立视觉设计系统。
- 快捷键系统。
- Command palette。
- Dock layout persistence。
- Project templates。
- Advanced inspector。
- Scene compare。
- Export presets。
- Documentation site。
- Tutorial examples。

验收标准：

- 新用户可以从 template 创建项目并完成一次仿真实验。
- 常用操作有快捷键和稳定反馈。
- UI 风格完全原创，不复制目标竞品表达。

## 当前进度总览（2026-07-15 审计）

```
代码规模：  ~1,600 行 Python (services/models) + ~1,400 行 TypeScript + ~4,000 行测试
测试：      47 passed，1 skipped
迭代记录：  16 个迭代日志
```

| 里程碑 | 状态 | 完成度 | 说明 |
|---------|------|--------|------|
| M0 Simulation-First MVP | ✅ 完成 | 100% | PySide6 shell、scene model、MJCF export、headless runner |
| M1 Local three.js Viewport | ✅ 第一版 | 80% | WebGL viewport、orbit、选择、gizmo、缺少 snap |
| M2 Robust Scene Editing | 🔶 基础完成 | 60% | dirty/undo/redo，缺少 hierarchy、duplicate、multi-select |
| M3 MuJoCo Live State Sync | ✅ 第一版 | 70% | Run/Pause/Step/Reset、pose sync，缺少 clock hardening |
| M4 Robot Import | 🔶 已开始 | 80% | runtime Link viewport sync 已完成，joint control 待接入 |
| M5 Physics Authoring | 🔶 部分完成 | 55% | primitive physics、material presets、collider debug，缺少 solver/constraints |
| M6 Timeline & Recording | ❌ 未开始 | 0% | 录制/回放/导出 trajectory |
| M7 Asset Pipeline | 🔶 部分完成 | 40% | OpenUSD mesh import，缺少 texture/material、asset library、thumbnails |
| M8 Controller API | 🔶 已开始 | 40% | joint target RPC、限位、slider 与 qpos/qvel 反馈已完成 |
| M9 Experiment/Env | 🔴 仅 stub | 5% | `SimLabEnv` 占位，不可训练 |
| M10 Diagnostics | 🔶 部分完成 | 35% | preflight validation、MJCF compile check，缺少独立 panel、soak tests |
| M11 Packaging | ❌ 未开始 | 0% | 无 installer、无版本信息 |
| M12 Polish | ❌ 未开始 | 0% | 视觉设计系统、快捷键系统、documentation site |

### 与竞品的差距快照

| 维度 | SimLab | OrcaLab | Isaac Sim/Lab | 差距等级 |
|------|--------|---------|---------------|----------|
| 场景编辑 | ✅ primitive + mesh | ✅ 宣称完整 | ✅ 成熟 | **小** |
| 机器人模型 | 🔶 有中间模型，无 importer/runtime | ✅ 宣称多形态 | ✅ 成熟 | **大（阻塞）** |
| 物理仿真 | 🔶 MuJoCo primitive | ✅ 宣称高精度 | ✅ PhysX/Newton | **中** |
| 实时渲染 | 🔶 three.js WebGL | ✅ 宣称高保真 | ✅ RTX | **中（可接受差距）** |
| 传感器 | ❌ 无 | ✅ 宣称 RGB/Depth/IMU/Lidar | ✅ 完整 | **大** |
| 控制器 | ❌ 无 | ✅ 宣称开放 | ✅ Python/ROS 2 | **大（阻塞）** |
| 训练环境 | ❌ 仅 stub | ✅ 宣称并发训练 | ✅ Isaac Lab | **大** |
| 资产生态 | 🔶 6 primitive + USD | ✅ 宣称 SimReady | ✅ 完整生态 | **中** |
| 部署 | 🔶 源码运行 | 🔶 PyPI conda | ✅ 完整矩阵 | **小（短期不追）** |

## 阶段性路线图（从 Gate 1 到 Gate 4）

### 🚀 Gate 1 — Robot Simulation Closure（P0，目标 2026-Q3）

**这是当前最关键的交付。** SimLab 还做不到真实机器人仿真闭环：不能导入机器人、不能控制关节、不能读取传感器。

| 次序 | 任务 | 预估工作量 | 验收标准 |
|------|------|-----------|----------|
| 1.1 | ✅ Robotics Intermediate Model 与共享 schema | S | 版本、round-trip、引用校验和旧 Scene 兼容已验证 |
| 1.2 | 外部 OpenUSD articulation importer 与 Import Report | L | 从磁盘导入 link/joint/drive/collider/inertial |
| 1.3 | Robot actor type + scene hierarchy 扩展 | M | Scene Tree 展示 robot→link→joint 层级 |
| 1.4 | Articulation 到 MJCF 转换 | L | 外部 USD 手臂导出后可由 MuJoCo 编译 |
| 1.5 | Joint/actuator/sensor runtime state bridge | M | 仿真时 joint state 同步到 viewport |
| 1.6 | Joint-space Controller API | M | UI 位置目标驱动至少两个 joint |
| 1.7 | Simulation clock hardening（固定步长、RTF、非阻塞）| L | 仿真不阻塞 UI 主线程，长时间运行稳定 |
| 1.8 | Gate 1 集成测试与外部资产演示 | S | 外部机械臂可导入→仿真→控制→保存 |

**Gate 1 验收**：从磁盘导入外部 OpenUSD 机器人手臂 → 在 viewport 中查看 link 结构 → 从 Property
Panel 修改 joint position target → MuJoCo 在重力、限位和碰撞约束下运行 → viewport 关节同步 →
save/reopen 行为一致。

### 🔧 Gate 2 — Professional Authoring & Debugging（P1，目标 2026-Q4）

| 次序 | 任务 | 优先级 |
|------|------|--------|
| 2.1 | Parent/child transform hierarchy + reparent | P0 |
| 2.2 | Dedicated collision prim、convex decomposition、collision layer/mask | P0 |
| 2.3 | World gravity、timestep、integrator、solver UI | P1 |
| 2.4 | 独立 Validation Panel（scene + asset + runtime） | P1 |
| 2.5 | Timeline、state recording、trajectory replay、CSV/JSON export | P1 |
| 2.6 | Project manifest、依赖复制、资产许可证、missing asset 修复 | P1 |
| 2.7 | Duplicate、multi-select、inline rename、context menu、autosave recovery | P1 |
| 2.8 | URDF import | P1 |

### 📡 Gate 3 — Sensor & Task Platform（P2，目标 2026-H1）

| 次序 | 任务 | 优先级 |
|------|------|--------|
| 3.1 | Joint state、IMU、contact/force 传感器（schema + runtime + UI） | P0 |
| 3.2 | 完整 `SimLabEnv` contract（obs/action spec、reward、termination、seed） | P0 |
| 3.3 | Headless batch runner + metrics + seed matrix | P2 |
| 3.4 | RGB/depth/segmentation 相机传感器（three.js 离屏渲染 MVP） | P2 |
| 3.5 | ROS 2 bridge（clock、TF、joint states、commands） | P2 |
| 3.6 | Domain randomization graph（pose、physics、material、light、noise） | P2 |
| 3.7 | Episode dataset export（manifest + 同步 sensor/state/action/reward） | P2 |
| 3.8 | 外部 RL library adapter（先接一个，不自研算法） | P2 |

### ⚡ Gate 4 — Scale & High Fidelity（P3，2026-H2+）

| 次序 | 任务 | 优先级 |
|------|------|--------|
| 4.1 | MuJoCo MJX / vectorized runtime 评估 | P3 |
| 4.2 | OpenUSD hierarchy round-trip（multi-body USD → SimLab → MJCF → USD） | P3 |
| 4.3 | 规模化合成数据管线（headless SDG + 断点续跑） | P3 |
| 4.4 | SIL/HIL adapters（external clock、realtime deadline、hardware I/O） | P3 |
| 4.5 | Windows/macOS packaging、installer、CI 矩阵 | P2 |
| 4.6 | Performance benchmark suite、24h soak tests、崩溃恢复 | P1 |

### 📊 为什么是这个顺序

1. **先关门再装修**：没有 robot import + controller，再多的面板也没法做真实机器人仿真。Gate 1 的 7 项任务是 P0 硬阻塞。
2. **传感器和训练环境建立在 controller 之上**：不先打通 joint command / observation 闭环，传感器数据和 RL env 无法验证。
3. **碰撞/层级/诊断是专业可用性门槛**：做到 Gate 2，SimLab 才算一个能日常使用的工具（不只是 demo）。
4. **规模化、高保真、ROS 2、分布式训练是差异化竞争**：但必须先有稳定基础；在 Gate 1-2 完成前不做过度工程化。
5. **打包是最后一步**：先保证功能闭环，再解决分发。源码运行在开发阶段足够。

### 与 OrcaLab/Isaac Sim 的差异化策略

- **不追 RTX 渲染**：three.js WebGL 对机器人编辑场景足够，高保真 sensor 仿真用离线/headless 后端。
- **不追云服务/Nucleus**：local-first、Git 友好的项目目录是核心竞争力。
- **不追 Omniverse/Kit 扩展系统**：保持 Python/TS 两层薄架构，降低复杂度。
- **追 MuJoCo 轻量优势**：可复现、易调试、单进程可控，比 PhysX 更适合研究和快速迭代。
- **追开放性**：scene.json + MJCF 都是人类可读文本格式，比二进制 USD 更易于版本控制和 diff。

## 近期迭代计划

### ✅ Iteration A - Simulation State Bridge（已完成）

日期：2026-07-09。交付：`MuJoCoSimulationSession`、`SimulationState` 数据结构、viewport `applySimulationState()`、Run/Pause/Step/Reset toolbar。

### ✅ Iteration B - Viewport Editing Tools（已完成）

日期：2026-07-09。交付：translate/rotate/scale gizmo、selection outline、frame selected、camera view shortcuts。剩余：snap to grid、viewport 集成测试。

### ✅ Iteration C - Scene Editing Reliability（第一版已完成）

日期：2026-07-09。交付：dirty state、undo/redo stack、`Ctrl+Z`/`Ctrl+Shift+Z`。剩余：duplicate actor、context menu、autosave recovery。

### ✅ Iteration F - Primitive Physics Playground（第一版已完成）

日期：2026-07-10。交付：Ground/Table/Ramp assets、static/dynamic primitive export、mass/friction editing、physics material presets、Collider Debug Overlay、visual/physics geometry fidelity pass。剩余：restitution editor、timestep/gravity UI、speed control。

### ✅ TypeScript Editor Migration（已完成）

日期：2026-07-10。交付：TS Editor Store 接管 scene/selection/dirty/undo/redo、QWebChannel JSON RPC bridge、MainWindow 缩减为单 QWebEngineView 容器。

### ✅ Physics Validation Preflight（已完成）

日期：2026-07-10。交付：Run/Step/Export 前校验 dynamic/static/mass/friction/geometry、MJCF compile 验证、actor/field 错误定位。

### ✅ OpenUSD Asset Import（已完成）

日期：2026-07-10。交付：`.usd/.usda/.usdc/.usdz` 导入、stage transform 与 up-axis 转换、`UsdGeomMesh` 三角化缓存、UsdPhysics 属性读取、mesh -> MJCF -> MuJoCo 闭环。

---

### 🔜 Iteration D - External OpenUSD Robot Arm Import（下一个 P0 里程碑）

日期：2026-07-Q3。目标：支持从磁盘导入外部 OpenUSD 机器人手臂。交付：Import Report、stage/dependency
loader、Prim hierarchy、UsdPhysics articulation/joint/drive/collider/inertial 映射和 Robot actor。

### 🔜 Iteration E - Validation Panel（P1）

日期：2026-07-Q3。目标：统一诊断入口。交付：validation report model、独立 UI panel、export preflight、quick fixes、依赖检查。

### 📋 Iteration G - Controller API（P0）

日期：2026-Q3。目标：per-step Python controller 闭环。交付：observation/action buffer、per-step callback、reset callback、异常隔离、position/velocity/PID 示例。

### 📋 Iteration H - Timeline & Recording（P1）

日期：2026-Q3。目标：仿真录制与回放。交付：timeline widget、state recording、trajectory replay、CSV/JSON export、速度控制。

### 📋 Iteration I - Sensor Platform（P0 依赖 C1/C2）

日期：2026-Q4。目标：物理传感器采样闭环。交付：joint state、IMU、contact/force sensor、统一 timestamp/frame/frequency/noise contract。

### 📋 Iteration J - Experiment & Env API（P0 依赖 C6）

日期：2026-Q4。目标：可训练 Gym-style 环境。交付：完整 `SimLabEnv`、`reset()/step()/close()`、observation/action spec、reward/termination hooks、seed control、headless batch runner。

## Definition of Done

每个 milestone 完成时必须满足：

- 功能可从 UI 或 documented command 触达。
- 有最小测试覆盖。
- README 或 docs 有更新。
- `docs/iterations/` 有本次迭代记录。
- `pytest` 通过。
- `ruff` 通过。
- 如引入第三方代码，必须记录许可证。
- 不引入 OrcaLab 品牌、素材、代码或表达复制。

## 当前风险

- QtWebEngine + three.js 的打包体积和平台兼容性需要后续验证。
- MuJoCo state 和 editor scene 的同步模型需要设计清楚，否则会混淆 authoring state 和 runtime state。
- Robot import 会涉及 mesh 路径、material、joint、actuator、sensor 等复杂模型。
- 只靠 `requirements.txt` 未 pin 精确版本，跨机器长期复现性仍可加强。
- 法务边界需要持续保持 clean-room 纪律，尤其是 UI 和示例资产。

## 长期愿景

SimLab 最终应成为一个本地优先、可扩展、可脚本化的机器人仿真工作台：

- 设计场景。
- 导入机器人。
- 配置物理参数。
- 编写控制器。
- 运行和回放仿真。
- 批量评估实验。
- 导出数据。
- 服务于机器人控制、强化学习、数字孪生和仿真验证工作流。
