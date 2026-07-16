# Project Controller Loader

日期：2026-07-16
提交：待提交

## 目标

让用户显式加载项目内外部 Python controller 文件，并驱动已导入的 OpenUSD 机械臂。

## 主要改动

- 新增 `ProjectControllerLoader`，只接受 resolved path 位于 project root 内的 `.py` 文件。
- 每次 Load 都读取并重新编译源码，避免 reload 命中旧 bytecode。
- 模块必须提供无参数 `create_controller()`，返回对象必须实现 reset/step。
- path validation、import、factory 和 validation 错误带 phase/path；import/factory 保存 traceback。
- SimulationService 保存当前 LoadedController metadata，并提供 load/reload 与 detach。
- EditorBridge 增加原生文件选择、显式 path load 和 detach RPC。
- Scene Open 不读取或执行 controller；controller 路径不写入 scene。

## 验证

- 同一路径源码改写后重新加载，position target 从 0.25 更新为 0.75。
- 项目根目录外路径、语法错误、缺失 factory 和非法 controller 均明确拒绝。
- 临时外部 Python 文件通过 Service 驱动 OpenUSD 双关节手臂 100 steps。
- 显式 Bridge RPC 加载、执行 5 steps、metadata 和 detach 状态通过。
- Loader/Bridge/Controller/Session 聚焦测试：38 passed；Ruff、Mypy 通过。

## 已知限制

- Controller 是 trusted in-process code，不是安全沙箱。
- TypeScript 尚无 Load/Reload/Detach Panel。
- Controller 文件暂不持久化到 scene，重开项目不会自动恢复或执行。

## 下一步

实现 TypeScript Controller Panel，并用原生确认保证只有显式用户操作才执行项目 Python 代码。
