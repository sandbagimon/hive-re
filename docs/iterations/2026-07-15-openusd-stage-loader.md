# OpenUSD Stage Loader and Import Report

日期：2026-07-15
提交：待提交

## 目标

为外部 OpenUSD 机器人资产建立统一、可诊断的 stage 打开和依赖解析入口，确保现有单 Mesh importer
与后续 articulation importer 不各自维护一套错误处理。

## 主要改动

- 新增 `ImportIssue` 和 `ImportReport`，稳定字段包括 severity、code、prim path、field、message 和
  fallback，并记录 resolved/unresolved dependencies。
- 新增 `load_openusd_stage()`；文件级失败抛出携带 report 的 `OpenUsdStageError`，可打开但依赖缺失
  的 stage 返回带 blocking issue 的结果。
- 使用 `UsdUtils.ComputeAllDependencies` 检测 reference、payload 和 asset 依赖，并关联 authored Prim
  与字段位置。
- 现有 `import_openusd_asset()` 改为复用 stage loader，保留原 API 和单刚体 Mesh 行为，同时在结果
  中提供结构化 report。
- 新增独立外部 USDA 双关节机械臂 fixture，包含 articulation root、三个 rigid body、fixed base、
  两个 revolute joint、position drive、collision、mass 和 diagonal inertia。
- fixture 为 SimLab 测试原创资产，附带明确许可证记录；importer 不包含文件名、Prim 名称或拓扑特判。

## 验证

- pxr 26.5 可打开外部 fixture，并识别 3 rigid bodies、2 revolute joints、2 angular drives 和
  3 collision prims。
- 缺失 reference 测试可报告 `usd.missing_dependency`、`/Broken` 和 `references` 字段。
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：51 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- `git diff --check`：通过。

## 已知限制

- 当前只打开和诊断 stage，尚未把 articulation 映射为 RoboticsModel。
- OpenUSD 会把部分 composition 警告直接写到 stderr；blocking dependency 仍由 ComputeAllDependencies
  稳定捕获。
- fixture 使用内嵌 primitive geometry；外部 mesh/reference 的成功复制将在 dependency resolver
  后续任务中实现。

## 下一步

实现 OpenUSD Physics articulation 到 RoboticsModel 的通用映射，首批覆盖 rigid body、mass/inertia、
visual/collider、fixed/revolute joint 和 angular position drive，并保留 source Prim path 和 stable ID。
