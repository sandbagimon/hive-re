# Algorithm and Simulation Backend Decoupling

日期：2026-07-29  
提交：`c215336` (`feat: complete frontend and simulation decoupling`)

## 目标

将训练算法从 MuJoCo、Web 编辑器和实时播放循环中分离。算法只依赖 Gymnasium 与稳定的
机器人语义 ID，同一任务能够在进程内 MuJoCo 和远程 gRPC 仿真后端之间切换；编辑器的
REST/WebSocket 控制面继续独立运行。

## 主要改动

- 定义 `SimulationBackend`、`SimulationBackendSession`、`SceneBundle`、
  `ModelDescription`、`ControlCommand` 和 `BackendState` 等引擎无关契约。
- 约束一个算法步为原子操作：应用完整控制向量、执行固定数量物理步、返回同一时刻状态，
  避免把 setter、`mj_step` 和状态查询拆成多次网络往返。
- 新增 `MujocoBackend` 进程内实现，并确保每个 Gym 环境独占 `MjData`、episode 和随机状态。
- 新增 gRPC 数据面以及 CreateSession、Reset、Step、Close RPC；远程请求只携带规范化场景
  和内容，不接受客户端服务器路径。
- 增加 schema hash 与稳定 body/joint/actuator 顺序，模型 revision 不匹配时立即拒绝旧动作。
- 增加 `DirectActuatorAdapter` 与 `JointTargetTask`，将稳定 actuator ID、动作范围、观测、
  reward、termination 和 truncation 与物理引擎分层。
- `BeeFoundrySimEnv` 保持标准 Gymnasium `reset/step/close` 接口，本地和远程后端不改变算法代码。
- 将编辑器 authoring state 与 simulation runtime state 分离；前端关闭或继续编辑时，独立的
  Gym/gRPC Session 不依赖 Three.js、FastAPI UI 刷新率或墙钟 sleep。
- 明确 REST + WebSocket 是编辑器资源控制面，gRPC 是高频固定步长算法数据面。
- 增加 `beefoundrysim-algorithm-server` 入口、algorithm/remote 可选依赖和独立部署说明。

## 验证

- 覆盖 Scene hash、schema 顺序、控制范围、固定 frame skip、Session 隔离和 close 语义。
- Gymnasium checker、相同 Task 在本地/远程后端切换、gRPC token 和真实 MuJoCo 路径通过。
- 前端 Store 测试确认编辑状态和运行状态不再互相覆盖。
- Ruff、Mypy、TypeScript typecheck、Python 回归和 Web E2E 纳入发布门禁。

## 已知限制

- 当前 gRPC 是明文传输；跨不可信网络仍需 TLS、短期凭据和部署层限流。
- 一个 `BeeFoundrySimEnv` 对应一个独占 Session，尚未提供服务端批量向量环境 RPC。
- Task/Robot Adapter 只提供最小关节目标垂直切片，WASD、机械臂末端任务和训练框架适配尚未
  形成统一任务库。
- REST/WebSocket 和 gRPC 共享场景语义，但尚未建立持久化 revision registry 与远程资产仓库。

## 下一步

- 增加 vectorized session/batched step，测量单机多环境吞吐和远程延迟。
- 为 Franka 增加稳定的关节组、末端执行器和 action profile。
- 在 gRPC 前增加 TLS、session quota、超时与可观测性。
- 建立 Scene revision 到训练 run/config/artifact 的可复现关联。
