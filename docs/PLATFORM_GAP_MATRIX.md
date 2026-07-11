# SimLab Platform Module Gap Matrix

评审日期：2026-07-10  
对标范围：SimLab 当前仓库、OrcaLab 公开资料、NVIDIA Isaac Sim 6.0 / Isaac Lab 公开资料

## 目的与口径

本文是平台能力差距的长期台账，回答三个问题：

1. SimLab 每个模块现在做到什么程度。
2. 对比 OrcaLab 和 Isaac Sim / Isaac Lab 还缺什么。
3. 下一次交付应如何验收，而不是只写“支持某功能”。

状态定义：

- **已有**：仓库中存在可使用实现，并有测试或可运行路径佐证。
- **部分**：主链路已存在，但只覆盖 primitive、单机场景或基础交互。
- **桩**：只有接口、占位类或路线图，没有真实闭环。
- **缺失**：仓库中没有对应实现。
- **产品选择**：与本地优先、clean-room 定位不一致，暂不追赶。

优先级定义：

- **P0**：真实机器人仿真闭环的阻塞项。
- **P1**：专业仿真编辑与调试的核心项。
- **P2**：数据、学习和规模化实验能力。
- **P3**：高保真、分布式和产业集成能力。
- **N/A**：当前明确不作为目标。

证据边界：SimLab 状态以本仓库代码和测试为准；OrcaLab 一栏仅记录官网和 PyPI 的公开表述，细粒度架构、格式兼容性和性能上限没有公开证据时标记为“未知”；Isaac Sim 与 Isaac Lab 分开看待，前者是仿真、传感器和合成数据平台，后者是建立在仿真平台上的机器人学习框架。

## 当前架构基线

SimLab 当前不是单体 Qt 面板应用，主要边界已经形成：

- **TypeScript Editor**：[`src/simlab/web_viewport/ts/`](../src/simlab/web_viewport/ts/) 负责界面、scene store、selection、dirty、undo/redo 和 three.js viewport。
- **Bridge Protocol**：[`shared/schemas/`](../shared/schemas/) 定义 scene、physics 和 RPC 数据契约；[`editor_bridge.py`](../src/simlab/editor_bridge.py) 承担 QtWebChannel RPC。
- **Scene Core**：[`src/simlab/models/`](../src/simlab/models/) 和 scene/project services 负责 Python 数据模型、保存、加载和基础校验。
- **Simulation Core**：[`src/simlab/services/`](../src/simlab/services/) 负责 primitive geometry contract、physics materials、preflight、MJCF export 和 MuJoCo session。
- **Experiment Stub**：[`gym_env.py`](../src/simlab/simulation/gym_env.py) 目前只有占位语义，尚不是可训练环境。

## A. 编辑器与场景核心

| 模块 | SimLab 当前状态 | OrcaLab 公开能力 | Isaac Sim / Lab 能力 | 主要差距与下一交付 | 优先级 |
|---|---|---|---|---|---|
| A1 桌面壳与工作区 | **已有**。PySide6 + QtWebEngine 薄壳，主要编辑器已迁移到 TypeScript。 | 公开展示完整本地仿真工作台；具体桌面壳架构未知。 | Omniverse Kit 应用、扩展和可配置工作区。 | 增加布局持久化、命令系统、崩溃恢复；保持 Python host 足够薄。 | P1 |
| A2 前端状态与 Bridge | **已有**。TS Store 管理 scene、selection、dirty、undo/redo，JSON RPC 调用 Python。 | 宣称提供 CLI、MCP 和 30+ 标准化 API；协议细节未知。 | Python API、Extensions、OmniGraph、命令和事件体系成熟。 | 给 bridge 增加协议版本、request id、错误码、异步任务、取消和超时；生成 TS/Python 类型。 | P1 |
| A3 Scene Schema 与版本迁移 | **部分**。共享 JSON Schema 和 `scene.version` 已有，迁移器未实现。 | 宣称以 OpenUSD 构建数据集；编辑场景内部 schema 未公开。 | OpenUSD 原生，具备 composition、references、variants、layers 和 schema 生态。 | 建立 schema migration、向后兼容测试、未知字段策略和 stable IDs；短期不迁移到 USD。 | P1 |
| A4 层级与变换系统 | **部分**。actor 为平面列表，primitive transform 可编辑。 | 支持复杂机器人和行业场景；层级实现未知。 | USD scene graph、xform hierarchy、articulation hierarchy 完整。 | 增加 parent/child、local/world transform、reparent、cycle validation 和层级序列化。 | P0 |
| A5 编辑工作流 | **部分**。选择、增删、属性编辑、dirty、undo/redo 已有。 | 公开资料展示场景构建工作流，编辑细节未知。 | Stage、Property、Content Browser、transform、复制、批量编辑等成熟。 | 完成 duplicate、multi-select、inline rename、typed inspector、search/filter、context menu、autosave recovery。 | P1 |
| A6 项目与资产引用 | **部分**。本地 metadata、primitive assets、scene save/open 和 OpenUSD mesh import/cache 已有。 | 宣称 SimReady 资产库和行业场景资产。 | Nucleus/本地 USD 资产、Content Browser、资产转换器与依赖体系。 | 定义 project manifest、完整 USD/texture 依赖复制、缩略图、许可证字段和 missing asset 修复。 | P0 |
| A7 可视化 Viewport | **部分**。three.js primitive/imported mesh、orbit、选择轮廓、translate/rotate/scale、相机快捷键已实现。 | 宣称高保真实时渲染；渲染后端和可调参数未知。 | RTX 实时/路径追踪、材质、灯光、相机和大型场景渲染。 | 补 PBR/texture、灯光、阴影、性能统计、snap 和 viewport 集成测试；不以追平 RTX 为短期目标。 | P1 |
| A8 几何与碰撞编辑 | **部分**。primitive contract、OpenUSD merged mesh collider、scale 烘焙、collider overlay 已有。 | 高精度物理为官网主张；碰撞 authoring 细节未知。 | primitive/mesh/convex/SDF colliders、collision approximation 和调试工具。 | 增加 dedicated collision prim、convex decomposition、collision layer/mask、compound collider、contact 可视化。 | P0 |
| A9 诊断与验证 | **部分**。Run/Step/Export preflight、MJCF compile、actor/field issue 已有。 | 宣称覆盖开发、验证和部署流程；诊断能力未知。 | Physics Debug、日志、Profiler、资产与 USD 检查工具较完整。 | 独立 Validation Panel、quick fix、依赖检查、运行时 warning 聚合、性能预算和 crash-safe log。 | P1 |

## B. 物理与机器人运行时

| 模块 | SimLab 当前状态 | OrcaLab 公开能力 | Isaac Sim / Lab 能力 | 主要差距与下一交付 | 优先级 |
|---|---|---|---|---|---|
| B1 物理引擎与仿真时钟 | **部分**。MuJoCo in-process Run/Pause/Step/Reset 和 pose sync 已有。 | 宣称高精度物理和大规模并发训练；引擎细节未完全公开。 | PhysX 与 Newton 路线、CPU/GPU 仿真、明确的 simulation/render clocks。 | 将 stepping 与 UI timer 解耦，增加 real-time factor、固定步长、catch-up policy、线程/进程隔离和长跑测试。 | P0 |
| B2 物理参数编辑 | **部分**。dynamic/static、mass/density、friction、contact presets 已有。 | 公开颗粒度不足。 | 刚体、关节、材质、solver、gravity、collision、terrain 等 authoring 完整。 | 增加 gravity、timestep、integrator、solver、inertia、contact 参数、constraints、tendons、heightfield UI。 | P1 |
| B3 Robot / Articulation 模型 | **缺失**。当前 Actor 不能表达 link、joint、actuator、sensor。 | 宣称支持多形态机器人训练。 | Articulation、joint、drive、actuator 和 robot schema 成熟。 | 先定义 Robot/Link/Joint/Actuator/Sensor schema，再扩展 scene hierarchy 和 runtime state，避免直接把 MJCF XML 塞进 Actor。 | P0 |
| B4 机器人与场景导入 | **缺失**。仅能导出 primitive MJCF。 | 宣称机器人/场景资产生态；公开格式矩阵不完整。 | 官方支持 CAD、URDF、MJCF、USD 等导入或转换路径。 | 第一阶段 MJCF import 保真闭环；第二阶段 URDF import；处理 mesh、material、include、default、compiler 和相对路径。 | P0 |
| B5 导出与格式互操作 | **部分**。primitive/OpenUSD mesh -> internal schema/cache -> MJCF 已有；没有 hierarchy/articulation round-trip。 | 宣称 OpenUSD 数据集；导入导出细节未知。 | USD 为核心，兼容多种机器人/资产格式并有 converter。 | 定义 USD/MJCF supported subset 和 loss report；补 hierarchy、material、dependency、articulation fixtures 和 package export。 | P1 |
| B6 执行器与控制器 | **缺失**。没有 actuator command path；controller API 仅在路线图。 | 宣称兼容主流强化学习平台并开放 API。 | 支持 articulation control、controllers、OmniGraph、Python 与 ROS control 路径。 | 实现 per-step controller、observation/action buffers、reset callback、异常隔离、position/velocity/PID 示例。 | P0 |
| B7 仿真状态、时间线与回放 | **部分**。当前只推送 body pose 和 simulation status。 | 官网描述完整训练验证流程；记录/回放细节未知。 | Timeline、simulation control、数据记录和回放生态完整。 | 增加 joint/actuator/sensor state、timeline、ring buffer、trajectory record/replay、CSV/JSON export。 | P1 |
| B8 确定性与复现 | **缺失**。没有统一 seed、配置快照或 replay hash。 | 并发训练能力有公开主张；确定性保证未知。 | 提供可配置仿真参数和学习工作流，但不同 GPU/物理配置仍需专门验证。 | 建立 seed contract、scene+engine config snapshot、版本指纹、determinism regression 和结果容差。 | P1 |

## C. 传感器、数据与机器人学习

| 模块 | SimLab 当前状态 | OrcaLab 公开能力 | Isaac Sim / Lab 能力 | 主要差距与下一交付 | 优先级 |
|---|---|---|---|---|---|
| C1 物理传感器 | **缺失**。Robot Sensor schema 和 runtime sample 均未实现。 | 官网列出 IMU、LiDAR，并提到多类机器人传感器。 | Camera、RTX LiDAR/Radar、IMU、contact、effort 等传感器体系。 | 先做 joint state、IMU、contact/force；统一 timestamp、frame、frequency、noise 和 buffer contract。 | P0 |
| C2 视觉传感器 | **缺失**。viewport 相机不是可采样的仿真 sensor。 | 官网列出 RGB、Depth。 | RTX camera、多种 annotator 和传感器模型成熟。 | three.js 离屏 camera MVP：RGB/depth/segmentation；随后评估高保真后端，不把编辑相机冒充 sensor。 | P2 |
| C3 中间件与 ROS 2 | **缺失**。无 ROS topic/service/clock/tf bridge。 | 宣称标准化 API 和生态兼容；ROS 版本与覆盖范围未明确。 | 官方 ROS 2 bridge、simulation control、sensor 和 TF 教程齐全。 | 建立 transport-neutral adapter，再实现 ROS 2 clock、TF、joint states、commands 和 selected sensors。 | P2 |
| C4 数据记录与标注 | **缺失**。无图像、标注或同步传感器数据集导出。 | 宣称 OpenUSD 数据集与数据采集工作流。 | Replicator、RGB/bbox/semantic/instance 等 annotators，支持常见数据格式工作流。 | 定义 episode manifest、同步时钟、state/sensor writers、2D/3D 标注 schema、COCO/KITTI adapter。 | P2 |
| C5 Domain Randomization / Sim2Real | **缺失**。没有参数分布、随机化阶段或审计记录。 | 官网强调仿真到部署的完整流程；具体随机化 API 未公开。 | Replicator randomization、Isaac Lab events/randomization 和 sim-to-real 工作流。 | 增加可复现 randomization graph：pose、physics、material、light、sensor noise，并记录每 episode 参数。 | P2 |
| C6 Task / Environment API | **桩**。`SimLabEnv.reset/step/close` 只返回占位数据。 | 宣称兼容主流强化学习平台。 | Isaac Lab 提供 manager-based/direct workflows、环境、任务和 wrappers。 | 定义 Env contract、observation/action specs、reward、termination、reset、seed、vectorization 边界并实现一个可训练任务。 | P0 |
| C7 强化学习与模仿学习 | **缺失**。无训练 runner、算法 adapter、demo buffer。 | 官网宣称强化学习训练及多机并发。 | Isaac Lab 集成 RL、imitation、motion planning 工作流和示例任务。 | 仿真平台只提供稳定 env API 与 adapters；先接一个外部 RL 库，避免自研算法框架。 | P2 |
| C8 运动规划与导航 | **缺失**。无 IK、规划器、地图或导航接口。 | 公开概述覆盖具身智能研发，具体 planner 未确认。 | Isaac 生态含运动规划、操控和导航相关工具链。 | 在 robot/control/sensor 稳定后接外部 IK/规划库；先定义 state/command/collision-query API。 | P3 |

## D. 规模化、扩展与交付

| 模块 | SimLab 当前状态 | OrcaLab 公开能力 | Isaac Sim / Lab 能力 | 主要差距与下一交付 | 优先级 |
|---|---|---|---|---|---|
| D1 Headless 与批处理 | **部分**。有 headless MuJoCo smoke runner，没有 task batch runner。 | 宣称多环境、多机器人并行训练。 | Isaac Sim 可 headless，Isaac Lab 支持大规模并行环境。 | 建立无 Qt 的 scene->env runner、batch spec、metrics、seed matrix 和失败隔离。 | P2 |
| D2 GPU 并行与分布式 | **缺失**。MuJoCo 单进程路径，没有 vectorized runtime。 | 宣称“万机并发训练”和多节点分布式。 | Isaac Lab 支持 GPU 并行、多 GPU 和多节点训练。 | 先测量 CPU batch 上限；再评估 MuJoCo MJX/vectorization；分布式排在 API 稳定之后。 | P3 |
| D3 合成数据规模化 | **缺失**。无 annotator、writer 或生成任务编排。 | 宣称数据采集和 OpenUSD 数据集能力。 | Replicator 提供随机化、annotator、writer 和大规模 SDG。 | 依赖 C2/C4/C5 后建立 headless generation job、数据校验、断点续跑和 dataset manifest。 | P3 |
| D4 扩展、插件与脚本 | **缺失**。目前只有内部 Python/TS 模块和固定 RPC。 | 宣称 MCP、CLI、30+ API。 | Kit Extensions、Python API、OmniGraph 和插件生态。 | 定义有版本的 public Python SDK、CLI 和插件 manifest；MCP 仅作为后续适配器，不与核心耦合。 | P2 |
| D5 SIL / HIL / 数字孪生 | **缺失**。无实时 I/O、硬件协议或时钟同步。 | 官网覆盖验证和部署阶段，具体 HIL 能力公开不足。 | Isaac Sim 官方定位包含 SIL/HIL 工作流与数字孪生场景。 | 先完成 deterministic clock、ROS 2 和 controller boundary，再设计 external clock、realtime deadline、hardware adapter。 | P3 |
| D6 性能、可靠性与可观测性 | **部分**。有 pytest/ruff/preflight，没有 profiler、telemetry 和 soak suite。 | 宣称大规模并发，公开 benchmark 方法有限。 | 提供 profiler、日志、性能优化指引和大场景实践。 | 建立 frame/step budgets、actor/geom scaling benchmark、内存监控、24h soak、crash bundle。 | P1 |
| D7 打包与硬件兼容 | **缺失**。当前依赖 conda/Python/Qt 系统库，曾出现 Linux xcb 依赖问题。 | PyPI 公布 Ubuntu 与 NVIDIA GPU 的最低建议配置，并宣称适配国产芯片。 | 有明确 workstation/container/cloud 部署和 GPU 兼容矩阵。 | 锁定依赖、Linux/Windows CI、Qt runtime 检查、安装包、容器化 headless runner、硬件矩阵。 | P1 |
| D8 文档、示例与许可证 | **部分**。README、iteration docs、demo scene、three.js license 已有。 | 官网/PyPI 提供产品概述和安装入口；细粒度开发文档公开有限。 | 官方文档、教程、样例、资产和 API reference 体系完整。 | 增加 versioned docs、robot walkthrough、API reference、example tests、第三方资产清单和 release checklist。 | P1 |
| D9 协作、云与账号 | **产品选择**。当前明确 local-first，无账号和云依赖。 | 官网展示账号、平台服务和产业生态入口。 | 可与 Nucleus、云部署和团队资产工作流结合。 | 近期不追赶。先保证项目目录可移植、Git 友好；远程资产库和协作服务需独立立项。 | N/A |

## 差距结论

SimLab 已经越过“只有 UI 原型”的阶段：primitive scene authoring、TS 编辑器状态、可见碰撞契约、MJCF preflight、MuJoCo 运行和 viewport pose sync 已形成一个小型闭环。当前最主要的问题不是再补一个面板，而是 scene model 仍以独立 primitive actor 为中心，尚不能表达真实机器人、控制、传感器和任务。

与两个对标平台相比：

- **对 OrcaLab**：SimLab 的本地、透明、可测试架构是差异化基础，但缺少其公开宣称的机器人资产、传感器、训练工作流、并发规模和标准化 API。
- **对 Isaac Sim**：SimLab 在体量和目标上不应直接追平 RTX/OpenUSD/Omniverse 全栈；应先把 MuJoCo 的轻量、可复现、易调试优势做实。差距最大的是 articulation/import、sensor、ROS 2、SDG 和规模化运行。
- **对 Isaac Lab**：当前 `SimLabEnv` 还是 stub，离 observation/action/reward/termination、可复现 reset 和 vectorized training 还有完整的一层平台工程。

## 建议执行顺序

### Gate 1 - Robot Simulation Closure（P0）

交付：

1. Robot/Link/Joint/Actuator/Sensor schema 与迁移规则。
2. MJCF importer、mesh dependency resolver 和 robot tree。
3. joint/actuator/sensor runtime state bridge。
4. controller per-step API 和异常隔离。
5. 非阻塞、固定步长 simulation clock。

验收：导入一个带 mesh、关节和 actuator 的开源 MJCF；从 UI 修改初始关节状态；运行 PID controller；viewport 与 joint state 同步；保存并重新打开后行为一致。

### Gate 2 - Professional Authoring and Debugging（P1）

交付：scene hierarchy、mesh collision、world/solver settings、Validation Panel、timeline/record/replay、project manifest 和 autosave recovery。

验收：一个含机器人、斜坡、接触材质和约束的项目可以编辑、验证、运行、录制、回放和迁移目录；所有失败都能定位到 actor/asset/field。

### Gate 3 - Sensor and Task Platform（P2）

交付：物理传感器、基础视觉传感器、完整 Env API、randomization、headless batch、ROS 2 基础 bridge、episode dataset。

验收：同一 task 可从 UI 和 headless API 运行；固定 seed 可复现；输出同步 observation/action/reward/sensor 数据；可接入一个外部 RL 库训练基础控制任务。

### Gate 4 - Scale and High Fidelity（P3）

交付：MJX/vectorized runtime 评估、GPU/多节点实验、OpenUSD hierarchy/round-trip 增强、规模化合成数据、SIL/HIL adapters。

验收必须先定义 benchmark 和目标硬件，不接受仅以“接口存在”宣告完成。

## 路线图覆盖缺口

现有 `PRODUCT_PLAN.md` 的 M0-M12 基本覆盖编辑器、物理、机器人、资产、控制器、实验、诊断和打包，但以下能力需要在对应 milestone 中显式补充：

- M4：Robot schema、articulation runtime state、物理传感器。
- M6：统一 simulation clock、trajectory manifest、确定性 replay。
- M7：project manifest、依赖解析、资产许可证和 mesh collision pipeline。
- M8：transport-neutral control API 与 ROS 2 adapter 边界。
- M9：完整 Env contract、randomization、headless batch 和外部 RL adapter。
- M10：性能 benchmark、soak tests、crash bundle 和 schema migration。
- 后续新 milestone：视觉传感器/合成数据、规模化 runtime、SIL/HIL；这些不应混入 Robot Import 的首个交付。

## 2026-07-10 审计更新

本次审计完成下列更新：

- **测试数量**：`pytest` 36 passed + 1 skipped（MuJoCo 条件跳过），TypeScript typecheck 通过，ruff 通过。
- **代码规模**：Python services/models ~1,600 行，TypeScript ~1,400 行，测试 ~4,000 行。
- **Gate 状态**：
  - Gate 0（已完成）：primitive scene authoring + TS 编辑器 + MJCF preflight + MuJoCo runner + viewport pose sync。
  - Gate 1（P0 阻塞）：robot schema + MJCF import + controller + clock hardening。**当前最紧急，预计 7 项任务，2-3 个迭代周期。**
  - Gate 2（P1 增强）：hierarchy + collision + validation panel + timeline + project manifest。
  - Gate 3（P2 平台）：sensors + env API + ROS 2 + randomization + headless batch。
  - Gate 4（P3 规模化）：MJX/GPU、USD round-trip、SDG、SIL/HIL。
- **与 OrcaLab 最大落差**：robot articulation、sensor 体系、训练环境、控制器 API。这些都是 Gate 1 + Gate 3 的范围。
- **与 Isaac Sim 最大落差**：RTX 渲染、OpenUSD 原生、传感器/标注器生态、GPU 并行。Gate 4 范围，短期不追。
- **差异化窗口**：MuJoCo 轻量可复现 + local-first + 人类可读文本格式（scene.json/MJCF），在研究和快速迭代场景有优势。

## 资料来源与限制

- [OrcaLab 官网](https://www.orca3d.cn/home.html)：高精度物理、高保真实时渲染、传感器、并发训练、OpenUSD、CLI/MCP/API 和完整工作流均来自厂商公开表述，本文未独立复测其性能或兼容范围。
- [OrcaLab PyPI](https://pypi.org/project/orca-lab/)：用于核对产品定位、资产/场景概述和公开硬件要求；页面的细粒度 feature 说明仍有限。
- [NVIDIA Isaac Sim 6.0 文档](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/index.html)：用于核对 OpenUSD、物理、传感器、ROS 2、Replicator 和机器人导入能力。
- [NVIDIA Isaac Sim 产品页](https://developer.nvidia.com/isaac/sim)：用于核对 CAD/URDF/MJCF、SIL/HIL、合成数据和平台定位。
- [NVIDIA Isaac Lab 产品页](https://developer.nvidia.com/isaac/lab)：用于区分仿真平台与机器人学习框架，并核对 RL、模仿学习、运动规划和多 GPU/多节点能力。

该矩阵是能力规划依据，不是兼容性承诺。每次 milestone 完成、竞品公开版本更新或架构边界变化时，应更新“评审日期”和对应行，不应只修改总结。
