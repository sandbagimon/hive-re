# 2026-08-10 物理引擎与实时仿真解耦

## 目标

在不破坏现有编辑器、机器人、无人机、抓取、轨迹、传感器和录制功能的前提下，消除
`SimulationService` 对 MuJoCo 的直接依赖，为 Newton 和刚体/水体组合求解器建立稳定扩展点。

## 完成内容

- 新增完整 `SimulationRuntimeSession` 和 `SimulationRuntimeBackend` 契约；
- 新增引擎能力模型、Scene 能力推导和 fail-fast 校验；
- 新增 `RuntimeBackendRegistry` 与 `beefoundrysim.runtime_backends` 插件发现；
- Scene 支持 `solvers.primary`、有序 `extensions` 和 `required_capabilities`；
- MuJoCo 被封装为默认 `MujocoRuntimeBackend`；
- `SimulationService` 不再导入 MuJoCo、不再读取 `model.opt.timestep` 或 `xml_path`；
- Web Preflight、Run、Step 和 Trajectory 加载通过所选 Runtime Backend；
- Stop 显式关闭 Runtime Session；
- Recording Schema 的 engine 从 MuJoCo 常量改为通用引擎标识；
- 增加无 MuJoCo Newton 替身端到端测试，并保留原有 MuJoCo 回归测试。

## 兼容性

- 未配置 `solvers` 的 Scene 仍默认使用 MuJoCo；
- REST 方法、WebSocket 事件和 `SimulationState` 结构未改变；
- `MuJoCoSimulationSession` 公共类继续保留，现有直接脚本与测试无需迁移；
- MJCF Export 继续作为显式 MuJoCo 工具可用。

## 后续扩展边界

Newton 只需注册新的 Runtime Backend；水体求解器由声明支持相应 extension 的主后端负责
双向耦合。当前未安装 Newton 或水体引擎，MuJoCo 对不支持的组合会明确报错，不会降级运行。
