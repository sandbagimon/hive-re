# 算法与仿真后端解耦

## 1. 完成后的边界

训练算法不再持有 MuJoCo 的 `MjModel/MjData`，也不依赖网页、Three.js、FastAPI
或实时播放时钟。算法只调用 Gymnasium 的 `reset/step/close`；同一个环境可以在本地
MuJoCo 和远程 gRPC 后端之间切换。

```text
RL / IL algorithm
       |
       | Gymnasium API
       v
SimLabEnv
       |
       +--> EnvironmentTask: observation / reward / termination / truncation
       |
       +--> RobotAdapter: semantic action <-> stable joint/actuator IDs
       |
       v
SimulationBackendSession
       |
       +--> MujocoBackend (in-process)
       |
       +--> GrpcSimulationBackend -- one atomic Step RPC --> MuJoCo server
```

网页实时仿真继续由 `SimulationService` 管理，但它现在只依赖
`SimulationRuntimeSession`，通过 `RuntimeBackendRegistry` 选择 MuJoCo、Newton 或未来的
组合求解器；训练环境不复用它的 Run/Pause、UI catch-up 或 WebSocket 状态。每个
`SimLabEnv` 创建并独占一个后端 Session，因此多个
环境之间没有 `MjData`、episode 计数器或随机数状态泄漏。

## 2. 稳定契约

`src/simlab/simulation/backend.py` 是引擎无关契约，核心对象如下：

- `SceneBundle`：规范化 Scene JSON、内容哈希，以及仅供本地适配器使用的部署路径；
- `ModelDescription`：timestep、scene/schema hash，以及按固定顺序排列的 body、joint、actuator；
- `BackendState`：紧凑只读数组，不包含 MuJoCo、USD 或 UI 对象；
- `ControlCommand`：绑定 `schema_hash` 的完整 actuator vector；
- `SimulationBackendSession`：`reset(seed, options)`、原子
  `step(command, physics_steps)`、`close()`；
- `SimulationBackend`：从不可变 Scene revision 创建隔离 Session。

数组顺序只能由 `ModelDescription` 决定，运行时不做名称扫描。Body position 是 xyz，
body quaternion 是 MuJoCo/后端数据面的 wxyz。命令和状态的 schema hash 不匹配时会
立即失败，避免模型更新后把旧动作写到错误 actuator。

一次 `step` 必须原子完成“应用完整控制向量 → 固定次数物理步进 → 读取同一时刻状态”。
远程实现也只发送一个 Step RPC，不把 actuator setter、`mj_step` 和状态查询拆成多次
网络往返。

## 3. Task 与 Robot Adapter

物理后端不知道 reward、episode 或键盘输入：

- `DirectActuatorAdapter` 用稳定 actuator ID 选择机器人，把 `[-1, 1]` 动作映射到
  各 actuator 的控制范围，并从 BackendState 提取关节 observation；
- `JointTargetTask` 实现一条可训练的垂直切片：目标关节位置、负误差 reward、成功
  termination 和固定 horizon truncation；
- 新任务应实现 `EnvironmentTask.bind(ModelDescription)`，reward 和 termination 不得
  下沉到 MuJoCo backend；
- WASD、轨迹和训练策略可以复用同一机器人语义适配层，但键盘事件不得放入 Gym Env。

## 4. 本地 Gymnasium 使用

安装算法依赖：

```bash
python -m pip install -e '.[algorithm]'
```

示例：

```python
import numpy as np

from simlab.services.project_service import load_scene
from simlab.simulation import (
    DirectActuatorAdapter,
    JointTargetTask,
    MujocoBackend,
    SceneBundle,
    SimLabEnv,
)

project_root = "/path/to/project"
scene = load_scene(f"{project_root}/scene.json")
task = JointTargetTask(
    robot=DirectActuatorAdapter(
        ["actuator_shoulder", "actuator_elbow"],
    ),
    target_positions=(0.6, -1.0),
    max_episode_steps=500,
)
env = SimLabEnv(
    backend=MujocoBackend(),
    scene_bundle=SceneBundle.from_scene(scene, asset_root=project_root),
    task=task,
    frame_skip=5,
)

observation, info = env.reset(seed=42)
observation, reward, terminated, truncated, info = env.step(
    np.array([0.2, -0.4], dtype=np.float32)
)
env.close()
```

这里 `frame_skip=5` 表示一个算法步执行五个固定物理步；它不使用墙钟 sleep，也不受
前端帧率影响。

## 5. 远程 gRPC 使用

安装远程依赖并在仿真服务器启动数据面：

```bash
python -m pip install -e '.[algorithm,remote]'
export SIMLAB_ALGORITHM_TOKEN='replace-with-a-random-token'
simlab-algorithm-server \
  --bind 127.0.0.1:50051 \
  --asset-root /srv/simlab/project
```

客户端只需替换 backend，Task 和算法代码保持不变：

```python
from simlab.simulation.grpc_backend import GrpcSimulationBackend

backend = GrpcSimulationBackend(
    "127.0.0.1:50051",
    token="replace-with-a-random-token",
)
env = SimLabEnv(
    backend=backend,
    scene_bundle=SceneBundle.from_scene(scene),
    task=task,
    frame_skip=5,
)
```

也可以让部署配置完成选择，Task 不读取该配置：

```python
from simlab.simulation import create_backend

backend = create_backend({"kind": "grpc", "target": "127.0.0.1:50051"})
```

gRPC 协议位于 `src/simlab/simulation/proto/algorithm_backend.proto`，包含
CreateSession、Reset、Step、Close。远程请求不接受客户端文件路径：MJCF 输出使用
服务端临时目录，场景引用的相对资产由服务端 `--asset-root` 解析。这样算法进程不需要
挂载仿真服务器的文件系统。

默认只绑定 `127.0.0.1`。远程开发时建议通过 SSH/VS Code 转发 50051；当前实现是
明文 gRPC，跨不可信网络部署前必须在反向代理或服务端增加 TLS，不能只依赖 token。

当前握手版本为 `simlab.algorithm.v2`。v2 在 body 状态中增加线速度和角速度，使四旋翼等
浮动基座机器人能够闭环控制；客户端和服务端版本不一致时会在创建 Session 阶段明确拒绝，
而不是静默错读状态数组。

## 6. 与 Web API 的关系

- `/api/v1` REST + WebSocket 是编辑器资源控制面和低频实时预览接口；
- gRPC 是训练算法的高频、固定步长数据面；
- 前端关闭后 Gym/gRPC episode 继续运行；
- 后端不会从 Three.js 读取渲染状态，算法也不会通过 REST 每步轮询；
- Scene authoring revision 与 Task 配置分开管理，同一场景可绑定多个任务。

这里存在两条不同但都引擎无关的契约：

- `SimulationBackendSession` 是算法数据面，强调紧凑数组和原子 Step，可经 gRPC 传输；
- `SimulationRuntimeSession` 是编辑器实时运行时，保持控制器、轨迹、传感器、抓取、
  录制和完整 `SimulationState` 功能。

二者不互相调用；具体 MuJoCo 代码分别位于各自的 adapter 中。详细扩展方式见
[`PHYSICS_RUNTIME_DECOUPLING.md`](PHYSICS_RUNTIME_DECOUPLING.md)。

## 7. 验证

```bash
python -m pytest -q \
  tests/test_simulation_backend.py \
  tests/test_gym_env.py \
  tests/test_grpc_backend.py
python -m mypy src/simlab/simulation
```

测试覆盖 Scene hash、稳定 schema、控制范围、原子多步、Session close、Gymnasium
checker、同一任务切换 backend、gRPC token，以及真实 MuJoCo 的本地/远程端到端路径。
