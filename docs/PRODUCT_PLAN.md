# SimLab Product Plan

日期：2026-07-09
状态：长期路线图
最近评审：2026-07-10

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
  - `pytest`：37 passed。
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

状态：未开始。

目标：

- 支持真实机器人模型，而不只是 primitive objects。

要实现：

- Robot/Link/Joint/Actuator/Sensor 共享 schema。
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

- 可导入一个开源机器人 MJCF/URDF。
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

## 优先级建议

近期最该做：

1. M4 Robot Import：先定义 Robot/Link/Joint/Actuator/Sensor schema，再完成最小 MJCF import。
2. M3 Runtime Hardening：固定步长、非阻塞 stepping、real-time factor 和长时间运行测试。
3. M8 Controller API：建立 actuator command、observation 和 per-step callback 闭环。
4. M6 Timeline/Recording：记录 joint/body/sensor state，并支持确定性 replay。
5. M10 Validation Panel：把已有 preflight 扩展成依赖、层级和运行时问题的统一入口。

理由：

- primitive authoring、MJCF export、MuJoCo 实时状态同步和编辑可靠性基础已经完成。
- 当前 scene model 仍是平面 primitive actor 列表，无法表达真实机器人 articulation。
- Robot schema、import、runtime state 和 controller 必须形成同一个 P0 交付链，避免只做到“看见机器人”却无法控制。
- 传感器、ROS 2、训练环境和规模化运行建立在这条闭环之上，按差距矩阵的 Gate 2-4 继续推进。

## 近期迭代计划

### Iteration A - Simulation State Bridge

状态：第一版已完成。

目标：

- 改造 SimulationService，使其支持 in-process stepping。
- 将 MuJoCo body poses 推送到 viewport。

交付：

- `MuJoCoSimulationSession`。
- `SimulationState` 数据结构。
- Viewport `applySimulationState()` JS API。
- Run/Pause/Step/Reset toolbar behavior。

### Iteration B - Viewport Editing Tools

状态：第一版已完成，仍需增强。

目标：

- 补齐编辑器基础操作。

交付：

- translate/rotate/scale mode。
- selection outline。
- frame selected。
- camera view shortcuts。

剩余：

- snap to grid。
- 更完整的 viewport smoke/integration tests。

### Iteration C - Scene Editing Reliability

状态：部分开始。

目标：

- 让用户编辑不会轻易丢数据。

已完成：

- dirty state。
- undo/redo stack。

剩余：

- duplicate actor。
- context menu。
- auto-save recovery file。

### Iteration D - Robot MJCF Import

目标：

- 支持导入开源 MJCF robot。

交付：

- MJCF import service。
- Robot actor。
- Mesh/reference handling。
- Robot tree view。

### Iteration E - Validation Panel

目标：

- 给用户清晰反馈 scene、asset、MJCF 的问题。

交付：

- validation report model。
- UI panel。
- export preflight checks。
- quick fixes。

### Iteration F - Primitive Physics Playground

状态：第一版已完成，仍需增强。

目标：

- 先让 primitive 场景具备可见的 MuJoCo 物理效果。

已完成：

- Ground/Table/Ramp assets。
- Static/dynamic primitive export。
- Dynamic/Mass/Friction property editing。
- Physics playground demo scene。
- Visual/physics geometry fidelity pass。
- Collider Debug Overlay。
- Physics material presets 和 density mode。
- 自动 bounds/pose/contact trajectory 验收。

剩余：

- restitution 和高级 contact 参数编辑器。
- timestep/gravity UI。
- simulation speed control。
- validation quick fixes 和独立 Validation Panel。

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
