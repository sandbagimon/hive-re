# Product Plan

日期：2026-07-09
提交：本次产品计划提交

## 目标

为 SimLab 制作完整产品计划，明确当前已经完成的能力、未来要实现的能力、全部 milestone、优先级和每个阶段的验收标准。

## 主要改动

- 新增 `docs/PRODUCT_PLAN.md`。
- 明确产品目标：
  - 本地优先机器人仿真编辑器。
  - MuJoCo 负责物理仿真。
  - PySide6 负责桌面应用。
  - three.js 负责不侵权的本地 3D viewport。
- 明确 clean-room 非侵权边界。
- 记录当前已经实现的能力：
  - 项目基础。
  - 桌面应用。
  - scene model。
  - 项目和场景服务。
  - primitive asset system。
  - three.js viewport。
  - MJCF exporter。
  - headless MuJoCo runner。
  - 测试。
- 规划 M0 到 M12 的完整 milestone。
- 给出近期 Iteration A 到 E 的执行顺序。
- 定义 milestone 的 Definition of Done。
- 记录当前主要风险。

## 验证

- 文档为 Markdown，无运行时改动。
- 后续提交前仍需跑 `pytest` 和 `ruff`，确保仓库状态健康。

## 已知限制

- 这是产品和工程路线图，不是法律意见。
- 具体机器人导入、MuJoCo live sync、打包分发仍需后续实现。

## 下一步

- 按计划优先推进 Iteration A：MuJoCo live state bridge。
