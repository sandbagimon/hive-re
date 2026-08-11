# 物理引擎与实时仿真运行时解耦

## 1. 当前结论

实时编辑器路径已经完成依赖倒置：REST/WebSocket、`WebApplication` 和
`SimulationService` 不再导入 MuJoCo Session，不读取 `MjModel/MjData`，也不假设运行时
产物一定是 MJCF。MuJoCo 是默认后端插件，不再是应用层基础类型。

```text
Browser
  |
  | REST + WebSocket (unchanged)
  v
WebApplication
  |
  v
SimulationService -- fixed wall clock / Run / Pause / Stop
  |
  | SimulationRuntimeSession
  v
RuntimeBackendRegistry -- selection + plugin discovery
  |
  +-- MujocoRuntimeBackend -> MuJoCoSimulationSession
  |
  +-- NewtonRuntimeBackend -> future adapter
  |
  `-- CoupledRuntimeBackend -> future rigid + fluid/particle extensions
```

现有前端状态、REST 方法和 WebSocket 事件没有改名。Run/Pause/Stop/Step/Reset、RTF、手动
关节和执行器控制、Python Controller、轨迹、传感器、抓取、无人机外力、Delivery Task、
录制和 MJCF 导出均继续可用。MJCF 导出是一个显式 MuJoCo 工具能力，不再决定 Live Run
使用哪个引擎。

## 2. 稳定契约

`src/simlab/simulation/runtime.py` 定义三类稳定对象：

- `SimulationRuntimeSession`：完整的实时仿真应用接口；
- `SimulationRuntimeBackend`：Preflight 和 Session Factory 插件接口；
- `EngineDescriptor`：引擎 ID、版本、能力集合和可组合扩展。

应用层只允许读取 Session 的：

- `engine_descriptor`；
- `timestep`；
- 可选 `artifact_path`；
- 通用 `SimulationState`；
- 控制、轨迹、录制和生命周期方法。

第三方引擎索引、原生指针、模型对象和缓存缓冲区不得越过该边界。

## 3. Scene 求解器配置

不写配置时保持原行为，默认使用 MuJoCo：

```json
{
  "simulation_config": {
    "timestep": 0.002,
    "duration": 10.0
  }
}
```

选择未来的 Newton 适配器：

```json
{
  "simulation_config": {
    "timestep": 0.002,
    "duration": 10.0,
    "solvers": {
      "primary": "newton",
      "extensions": []
    }
  }
}
```

声明刚体与水体耦合拓扑：

```json
{
  "simulation_config": {
    "timestep": 0.001,
    "duration": 10.0,
    "solvers": {
      "primary": "newton",
      "extensions": ["water-sph"]
    },
    "required_capabilities": ["rigid_body", "fluid"]
  }
}
```

`extensions` 是有序组合请求，不是标签。主后端必须真正实现同一时间轴、稳定 Entity ID、
边界条件同步和力/冲量双向回写。当前 MuJoCo 后端没有声明水体组合能力，所以会在
Preflight/Create Session 阶段明确拒绝上述配置，不会静默使用无水体的近似结果。

## 4. 能力协商

Scene 会自动推导刚体、碰撞、关节、约束、外力和射线查询等需求，也可通过
`required_capabilities` 显式声明：

```text
rigid_body | articulation | collision | constraint | external_force
ray_query | kinematic_actor | fluid | particle | deformable_body | differentiable
```

Backend 的 `EngineDescriptor.capabilities` 必须覆盖需求。缺失能力会在加载原生引擎模型前
失败，从而避免“能打开但结果被悄悄简化”的不可复现状态。

## 5. 接入 Newton

Newton adapter 应作为独立模块或独立 Python 包实现：

```python
class NewtonRuntimeBackend:
    @property
    def descriptor(self) -> EngineDescriptor:
        ...

    def preflight(self, request: RuntimeSessionRequest) -> RuntimePreflightReport:
        ...

    def create_session(self, request: RuntimeSessionRequest) -> SimulationRuntimeSession:
        ...
```

外部包通过 entry point 注册，不需要修改 `SimulationService`、REST 路由或前端：

```toml
[project.entry-points."simlab.runtime_backends"]
newton = "simlab_newton.runtime:NewtonRuntimeBackend"
```

最低兼容门槛是实现完整 Session 契约，并通过替换后端测试以及现有机器人、无人机、抓取、
轨迹、传感器和录制一致性测试。状态和命令必须使用 Scene 中的稳定 ID，不得把 Newton
索引暴露给上层。

## 6. 接入水体或其他扩展求解器

水体不是简单把 `engine="water"` 换掉，因为场景通常仍需要刚体/关节主求解器。推荐由一个
支持组合的主 Runtime Backend 在内部负责：

1. 用主引擎建立权威时间轴和刚体状态；
2. 将刚体边界和速度同步到水体求解器；
3. 执行水体子步或多速率步进；
4. 将压力、浮力、阻力和冲量回写主引擎；
5. 完成主引擎步进后发布一个一致的 `SimulationState`；
6. Reset、recording metadata、错误和 close 必须覆盖整个 solver stack。

具体耦合数据留在 adapter 内。只有稳定 Entity ID、时间、状态和诊断信息可以进入公共契约。
如果未来需要把高带宽流体场传给可视化，应新增版本化 Field/Particle 数据面，不应把大型网格
塞进现有 Actor `SimulationState` 或每帧 REST 响应。

## 7. 与算法后端、REST 和 gRPC 的关系

- REST/WebSocket 是编辑器控制面，协议保持不变；
- `SimulationRuntimeSession` 是实时编辑器的完整功能契约；
- `SimulationBackendSession` 是 Gymnasium/算法的紧凑原子 Step 契约；
- gRPC 是算法数据面的部署方式，不是物理引擎类型；
- MuJoCo/Newton/组合求解器是引擎选择，不是 HTTP/gRPC 传输选择。

因此将来既可以本地运行 Newton，也可以再为 Newton 实现算法 Backend 并经同一 gRPC 数据面
远程运行，而不要求改 Task 或前端。

## 8. 验证

```bash
python -m pytest -q \
  tests/test_runtime_backend.py \
  tests/test_simulation_clock.py \
  tests/test_simulation_session.py \
  tests/test_web_application.py
python -m mypy src/simlab/simulation src/simlab/services/simulation_service.py
```

`tests/test_runtime_backend.py` 使用一个不导入 MuJoCo 的 Newton 替身，验证 Web Preflight、Run、
固定步进、Stop、求解器选择、能力缺失和不支持组合的 fail-fast 行为。
