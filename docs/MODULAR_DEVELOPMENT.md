# SimLab 模块化开发指南

## 1. 文档目的

本文定义 SimLab 的模块边界、依赖方向、代码组织方式和渐进式重构路线，用于指导后续功能开发、代码评审和测试建设。

本文描述的是目标架构。现有代码已经具备前后端独立部署、领域模型、仿真服务和传感器子模块等基础，但部分物理文件仍承载多个职责。模块化工作应当以小步迁移完成，不应为了调整目录一次性重写已经验证过的业务逻辑。

## 2. 当前运行架构

SimLab 当前由独立 Web 前端、Python API 后端、仿真核心和共享数据契约组成：

```text
Browser / optional Qt web shell
              |
              | HTTP REST + WebSocket
              v
TypeScript editor --> FastAPI v1 API --> ResourceManager
     |                                      |
     |                                      v
     +-- three.js viewport             WebApplication
                                             |
                                             v
                                     SimulationService
                                             |
                                             v
                                   MuJoCoSimulationSession
```

运行边界如下：

- 前端是可独立构建和部署的静态 Web 应用。
- 后端是可独立启动的 Python API 服务。
- HTTP API 负责资源管理和控制命令，WebSocket 负责实时仿真事件。
- 前后端只通过版本化网络契约通信，不共享进程、内存或文件路径。
- Qt 程序只是可选网页容器，不承担业务逻辑。

## 3. 模块化原则

### 3.1 单一职责

一个模块应当只有一个主要变化原因。例如，Three.js 渲染变化不应要求修改 REST 路由，API 鉴权变化也不应影响 MuJoCo Session。

### 3.2 依赖单向流动

允许的总体依赖方向是：

```text
UI / API Adapter
       |
       v
Application Use Cases
       |
       v
Domain Model
       ^
       |
Infrastructure Adapters
```

领域模型不得反向依赖 FastAPI、Three.js、Qt、MuJoCo HTTP 服务或浏览器 API。MuJoCo、OpenUSD、文件存储等外部能力应当由应用层通过明确接口调用。

### 3.3 明确状态所有权

- 前端 `EditorStore` 拥有场景创作状态、选择状态、Dirty 状态和 Undo/Redo 历史。
- Project Resource 拥有后端规范化场景、项目资产和 revision。
- Simulation Resource 拥有一次隔离的仿真运行时。
- MuJoCo Session 拥有物理状态、仿真时间和运行时控制状态。
- Artifact Resource 拥有可下载输出的元数据和内容。

仿真位姿不应直接写回创作 Transform；需要持久化仿真结果时，应通过显式的“烘焙”或“应用运行状态”用例完成。

### 3.4 通过契约协作

模块之间优先传递领域对象、明确的 DTO 或版本化事件，不传递无法约束的内部字典、绝对文件路径和第三方库对象。

跨前后端数据格式以 `shared/schemas/` 和 `/api/v1/openapi.json` 为准。任何破坏性契约修改都必须创建新的 API 版本或提供兼容迁移。

### 3.5 渐进式迁移

模块化重构必须保持以下基线持续可用：

- 场景打开、编辑和保存；
- 资产列表与 OpenUSD 导入；
- Preflight 和 MJCF 导出；
- Run、Pause、Step、Reset；
- WebSocket 状态同步和断线恢复；
- 轨迹、控制器、传感器和录制功能。

## 4. 目标模块划分

### 4.1 Web 前端

#### App Shell

职责：

- 应用启动与依赖装配；
- 全局布局；
- 顶层错误边界；
- 页面生命周期；
- 将 Store、API Client、Viewport 和各面板组合起来。

App Shell 不实现具体面板 HTML，也不直接拼装 REST 请求。

#### Editor State

职责：

- Scene 创作状态；
- Actor 增删改；
- 当前选择；
- Dirty tracking；
- Undo/Redo；
- 编辑命令和派生选择器。

核心代码来源：`frontend/src/ts/store.ts`。

#### Viewport

职责：

- Three.js Scene、Camera 和 Renderer；
- Primitive、导入 Mesh 和 Robot Link 渲染；
- 选择、Gizmo、相机预设和碰撞体调试；
- 将运行时位姿应用到可视对象；
- GPU 资源释放。

Viewport 不负责保存项目、创建仿真实例或显示业务 Toast。

#### API Client

职责：

- 读取 `simlab-config.json`；
- REST 请求和统一错误处理；
- Bearer Token；
- Project/Simulation ID 生命周期；
- WebSocket 连接、重连和事件补发；
- API 版本兼容检查。

建议将当前 `EditorBridgeClient` 更名为 `SimLabApiClient`。名称迁移不应改变公共行为。

#### Feature Panels

前端业务面板按功能拆分：

| 模块 | 主要职责 |
|---|---|
| `assets` | 资产加载、搜索、添加和 OpenUSD 上传 |
| `scene-tree` | Actor/Robot/Link 层级和选择 |
| `inspector` | Transform、Physics、Joint、Sensor 属性编辑 |
| `validation` | Preflight 问题展示和字段定位 |
| `trajectory` | 关键帧草稿、保存、加载和播放控制 |
| `recording` | 信号选择、录制状态和产物下载 |
| `controller` | 控制器上传、重载、卸载和运行状态 |
| `console` | 结构化消息和运行日志 |
| `simulation-toolbar` | Run/Pause/Step/Reset、速度和 RTF |

每个面板应通过显式输入和回调访问 Store 或 Application Controller，避免直接引用其他面板的 DOM。

### 4.2 后端 API 与应用层

#### API Adapter

职责：

- FastAPI 路由；
- 请求 DTO 和响应 DTO；
- HTTP 状态码；
- 鉴权和 CORS；
- WebSocket 协议；
- 领域错误到 API 错误的映射。

API Adapter 不直接操作 MuJoCo 数据，也不把服务器绝对路径返回给浏览器。

#### Application Use Cases

职责：

- 编排一个完整用户操作；
- 管理事务性顺序和错误边界；
- 调用领域服务和基础设施适配器；
- 发布应用事件。

建议形成明确用例，例如：

```text
CreateProject
UpdateProjectScene
ImportOpenUsdAsset
RunPhysicsPreflight
ExportMjcfArtifact
CreateSimulation
RunSimulation
SetJointTargets
LoadTrajectory
StartRecording
AttachController
```

当前 `WebApplication.dispatch()` 中的字符串方法映射可以逐步替换为这些显式用例；REST API 不需要等待内部迁移即可保持稳定。

#### Resource Lifecycle

职责：

- Project、Simulation 和 Artifact 资源生命周期；
- ID 生成和资源隔离；
- Project 与 Simulation 归属关系；
- 项目更新后的相关仿真失效；
- 资源关闭和后台线程清理。

当前实现来源：`src/simlab/resources.py`。

#### Persistence

职责：

- 数据根目录管理；
- 项目场景持久化；
- 资产缓存；
- Artifact 内容存储；
- 路径规范化和 traversal 防护。

应用层只使用资源 ID 或项目相对引用。Persistence 模块负责把这些引用解析成后端路径。

### 4.3 领域与转换模块

#### Scene Domain

包含：

- Scene；
- Actor；
- Transform；
- Physics 属性；
- Physics Material；
- Scene Trajectory 引用。

#### Robotics Domain

包含：

- Articulation；
- Link；
- Joint；
- Actuator；
- Collider；
- Inertial；
- Sensor；
- Sensor Noise。

#### Import Pipeline

职责：

- OpenUSD Stage 加载；
- 单位、Up Axis 和 Transform 转换；
- Mesh 提取；
- Articulation 映射；
- Visual/Collision/Robotics Cache；
- Import Report 和不支持能力报告。

导入模块输出 SimLab 领域模型和项目相对缓存引用，不输出供前端直接使用的 USD Python 对象。

#### Validation and Export

职责：

- Scene Schema 校验；
- Robotics 拓扑和引用校验；
- Physics Preflight；
- MJCF 生成；
- MuJoCo 编译检查；
- 可定位到 actor/field 的问题报告。

验证模块不得修改传入的 Scene。

### 4.4 仿真运行时

#### Simulation Orchestrator

职责：

- Session 创建与销毁；
- 后台固定时钟调度；
- Run/Pause/Step/Reset；
- Target RTF 与 Actual RTF；
- 运行时异常隔离；
- 状态和日志事件发布。

#### MuJoCo Session

职责：

- `MjModel` 和 `MjData` 生命周期；
- 固定物理步进；
- Actor/Link/Joint/Actuator 映射；
- 读取不可变 SimulationState；
- 接收已经验证的控制输入。

Session 应当组合控制、轨迹、传感器和录制组件，而不是重新实现这些组件的业务规则。

#### Control

职责：

- 手动 Joint Target；
- 轨迹控制；
- Python Controller；
- 控制超时 Watchdog；
- 控制源互斥；
- 控制器错误和 deadline 隔离。

支持的控制源应显式建模：

```text
manual | trajectory | python-controller
```

在同一仿真实例中，同一时刻只能有一个活动控制源。

#### Sensors

按传感器种类拆分：

- Joint State；
- IMU；
- Contact；
- Noise Sampling；
- MuJoCo Contact Adapter。

所有传感器使用物理 step index 调度，不依赖浏览器帧率或 WebSocket 推送频率。

#### Recording

职责：

- 固定步长采样；
- Sensor Event 合并；
- 最大样本数限制；
- JSON/CSV 编码；
- Recording Artifact 创建。

录制格式转换不应写入 MuJoCo Session 内部状态。

### 4.5 共享契约与外围适配器

#### Shared Contracts

`shared/schemas/` 是跨语言数据契约的权威来源，包含 Scene、Physics、Robotics、Trajectory 和 Recording Schema。

后续可以增加自动代码生成：

```text
JSON Schema
   |-- generate --> TypeScript interfaces
   `-- validate --> Python domain serialization
```

自动生成代码必须输出到独立目录，业务代码不得手工修改生成结果。

#### Optional Qt Shell

Qt Shell 只负责打开一个 HTTP(S) 前端地址。它不得：

- 启动或关闭 API 服务；
- 通过 QWebChannel 暴露业务对象；
- 访问项目内部路径；
- 成为浏览器功能的必要依赖。

`editor_bridge.py` 是未接入当前产品入口的历史兼容代码。删除它之前，应先迁移或删除对应旧测试，并确认没有外部调用者。

## 5. 目标物理目录

下面是建议的目标结构。目录迁移可以分阶段进行，不要求一次完成。

```text
frontend/src/ts/
├─ app/
│  ├─ bootstrap.ts
│  └─ app-shell.ts
├─ api/
│  ├─ client.ts
│  ├─ websocket.ts
│  └─ runtime-config.ts
├─ editor/
│  ├─ store.ts
│  ├─ commands.ts
│  └─ selectors.ts
├─ viewport/
│  ├─ viewport.ts
│  ├─ geometry.ts
│  └─ runtime-state.ts
├─ features/
│  ├─ assets/
│  ├─ inspector/
│  ├─ scene-tree/
│  ├─ simulation/
│  ├─ trajectory/
│  ├─ recording/
│  └─ controller/
└─ contracts/
   └─ types.ts

src/simlab/
├─ api/
│  ├─ app.py
│  ├─ dependencies.py
│  ├─ errors.py
│  ├─ http_v1.py
│  └─ websocket_v1.py
├─ application/
│  ├─ projects.py
│  ├─ simulations.py
│  ├─ artifacts.py
│  └─ events.py
├─ domain/
│  ├─ scene/
│  ├─ robotics/
│  ├─ trajectory/
│  └─ recording/
├─ importers/
│  └─ openusd/
├─ exporters/
│  └─ mjcf.py
├─ simulation/
│  ├─ orchestrator.py
│  ├─ session.py
│  ├─ control/
│  ├─ sensors/
│  └─ recording/
├─ infrastructure/
│  ├─ persistence/
│  └─ artifacts/
└─ desktop/
   └─ qt_shell.py
```

## 6. 依赖规则

| 调用方 | 允许依赖 | 禁止直接依赖 |
|---|---|---|
| 前端面板 | Store、API Client、公共 UI 工具 | FastAPI、后端路径、其他面板 DOM |
| Viewport | 前端类型、几何契约、运行时状态 | REST 路由、项目存储、MuJoCo 对象 |
| API Adapter | DTO、应用用例、鉴权服务 | `MjData`、USD Stage、前端实现 |
| Application | Domain、资源接口、仿真接口 | 浏览器 DOM、FastAPI Request |
| Domain | Python 标准库和领域内模块 | FastAPI、Qt、文件系统、MuJoCo |
| Import/Export | Domain、受控基础设施接口 | 前端 Store、HTTP Response |
| Simulation | Domain、控制、传感器、MuJoCo Adapter | FastAPI、Three.js、Qt |
| Persistence | Domain 序列化、受控文件根目录 | UI 和仿真调度逻辑 |

建议在代码评审时把违反依赖方向视为架构问题，而不仅是代码风格问题。

## 7. 关键模块契约

### 7.1 Scene 同步

```text
EditorStore
  -> serialize Scene DTO
  -> PUT /projects/{id}/scene
  -> validate and canonicalize
  -> increment project revision
  -> invalidate stale simulation state
```

前端不得假设提交的数据未经后端规范化。服务端返回的 canonical scene 是最终网络表示。

### 7.2 仿真创建与运行

```text
POST /simulations
  -> create isolated Simulation Resource
  -> build application/session boundary

POST /simulations/{id}/run
  -> preflight
  -> compile MJCF
  -> start fixed-step clock

WS /simulations/{id}/events
  -> snapshot
  -> ordered state/status/console events
  -> heartbeat and reconnect replay
```

每个仿真实例必须拥有独立状态，不能使用进程级全局 MuJoCo Session。

### 7.3 Artifact

导入缓存和下载产物对外使用 opaque ID：

```text
art_xxx -> backend-owned path/content
```

API 不得返回绝对服务器路径。浏览器也不得把本地路径字符串当作服务器可访问路径发送。

### 7.4 实时事件

每个 WebSocket 事件至少包含：

```json
{
  "version": "v1",
  "simulation_id": "sim_xxx",
  "sequence": 42,
  "type": "state",
  "payload": {}
}
```

新增事件类型时必须保证旧客户端可以忽略未知事件。改变已有字段语义属于破坏性变更。

## 8. 模块化迁移路线

### 阶段 0：保护现有行为

在移动代码前固定以下测试基线：

```bash
python -m pytest
npm run typecheck
npm run test:frontend
npm run test:web
```

重构阶段不得以删除 E2E 覆盖来换取目录迁移。

### 阶段 1：拆分前端 `app.ts`

推荐顺序：

1. 提取无状态 HTML/render helpers；
2. 提取 Console、Validation、Assets 和 Scene Tree；
3. 提取 Trajectory、Recording 和 Controller 面板；
4. 提取 Simulation Controller；
5. 让 `app.ts` 只负责启动和模块装配。

每次提取一个面板，同时增加对应的 DOM 或纯逻辑测试。

### 阶段 2：拆分仿真 Session

推荐顺序：

1. 保留 `MuJoCoSimulationSession` 公共接口；
2. 提取状态映射器；
3. 提取 Control Source Coordinator；
4. 提取 Sensor Runtime；
5. 提取 Recording Runtime；
6. Session 只保留 MuJoCo 生命周期和单步编排。

固定时钟、Reset 可重复性和录制确定性必须在每一步迁移后验证。

### 阶段 3：显式应用用例

逐步用类型明确的应用服务替换 `WebApplication.dispatch(method, args)`：

- API Route 直接调用应用用例；
- 统一应用错误类型；
- 事件发布接口从应用服务中抽离；
- 保持 `/api/v1` 路由和响应兼容。

### 阶段 4：提取 Persistence 和 Artifact Store

把目录创建、文件读取、缓存复制和 Artifact 保存从 `ResourceManager` 中移出，使资源管理器专注生命周期与关联关系。

### 阶段 5：统一契约生成

- 校验所有共享 Schema；
- 从 Schema 生成 TypeScript 类型；
- 对比 Python `to_dict/from_dict` 的兼容性；
- 在 CI 中检测生成结果是否过期。

### 阶段 6：清理兼容代码

- 将 `EditorBridgeClient` 更名为与 HTTP 职责一致的名称；
- 确认旧 Qt WebChannel 没有产品调用者；
- 删除或归档 `editor_bridge.py`；
- 更新过时架构文档和测试名称。

## 9. 新功能开发流程

一个新功能应按以下顺序设计：

1. 确定状态归属和所属业务模块；
2. 定义或扩展领域模型；
3. 更新共享 Schema，并加入兼容测试；
4. 实现后端用例和单元测试；
5. 必要时增加 REST/WebSocket 契约；
6. 更新 TypeScript 类型和 API Client；
7. 实现独立前端 Feature；
8. 增加端到端验收测试；
9. 更新用户文档和模块所有权说明。

不应从 UI 事件处理器开始临时扩展后端内部字段，再回头补领域模型。这会造成网络契约和业务状态失去统一来源。

## 10. 测试边界

### Domain Tests

- 无网络、无 UI；
- 场景和机器人序列化；
- Validation；
- Trajectory 和 Recording 数据规则。

### Service Tests

- OpenUSD 导入；
- MJCF 导出；
- MuJoCo Session；
- 控制器；
- 传感器；
- 固定时钟和确定性。

### API Contract Tests

- HTTP 方法、状态码和错误格式；
- 鉴权；
- 资源隔离；
- Artifact 下载；
- WebSocket snapshot、sequence、heartbeat 和 replay。

### Frontend Unit Tests

- Store；
- Undo/Redo；
- Trajectory Draft；
- API Client 的 URL、恢复和错误映射；
- 面板纯逻辑和事件绑定。

### Browser E2E Tests

- 页面启动与资产恢复；
- Open/Save；
- 编辑、导入、导出；
- Run/Pause/Step/Reset；
- 轨迹、控制器和录制；
- 前后端不同端口；
- WebSocket 断开重连；
- 多客户端资源隔离。

## 11. 模块完成标准

一个模块或模块化迁移任务只有在以下条件全部满足时才算完成：

- 职责和公共接口有文档；
- 不违反本文依赖方向；
- 不暴露后端绝对路径或第三方内部对象；
- 输入和输出有明确类型；
- 失败模式有稳定错误表示；
- 单元测试覆盖核心规则；
- 涉及跨进程行为时有 API 或 E2E 测试；
- 类型检查、Python 测试和 Web 测试通过；
- 没有把旧模块和新模块同时作为两个事实来源；
- 相关架构文档已经更新。

## 12. 当前优先级建议

按收益和风险排序，建议优先执行：

1. 拆分前端 `app.ts`，降低 UI 功能相互影响；
2. 拆分 `simulation_session.py` 的控制、传感器和录制编排；
3. 将 `WebApplication` 的字符串 dispatch 转换为显式应用用例；
4. 将 Persistence/Artifact Store 从 `ResourceManager` 提取；
5. 建立 Schema 到 TypeScript 类型的自动生成；
6. 清理 Qt WebChannel 历史兼容代码。

这些工作只调整内部模块结构，不要求更改现有 `/api/v1` 公共接口，也不改变前后端独立部署方式。
