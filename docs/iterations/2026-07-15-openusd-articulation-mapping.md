# OpenUSD Articulation Mapping

日期：2026-07-15
提交：待提交

## 目标

把外部 OpenUSD 机械臂中的物理层级映射到版本化 RoboticsModel，不依赖资产文件名、显示名称或
固定 Prim 拓扑，并保持现有单 Mesh importer 不变。

## 主要改动

- 新增 `import_openusd_articulations()` 和结构化结果/异常类型。
- 通过 `PhysicsArticulationRootAPI`、RigidBody relationship 和 Joint body target 重建 Link 层级。
- 首批映射 Fixed/Revolute Joint、joint axis/limit/origin、angular position Drive target、stiffness、
  damping 和 max force。
- 映射 MassAPI 的 mass、center of mass、diagonal inertia，并应用 stage units 与 Y-up/Z-up 转换。
- 将可见 Gprim 与 CollisionAPI Prim 分别映射为 VisualGeometry 和 Collider；primitive scale 烘焙到
  size，非均匀 sphere 映射为 ellipsoid。
- stable ID 由实体种类和 Prim path 哈希生成，显示名称只作为 UI 文本。
- 不支持的 joint 或无法解析的关系写入 Import Report，不静默伪装成可运行关节。

## 验证

- 外部 USDA fixture 映射为 fixed base、3 links、2 revolute joints 和 2 position actuators。
- 验证 mass、center of mass、diagonal inertia、joint limit、initial target、gain 和 max force。
- 将所有 fixture Prim 名称替换后仍按 relationships 得到正确拓扑。
- 验证厘米制 Y-up stage 的 link/geometry/center of mass/inertia 转换。
- RoboticsModel JSON round-trip 通过，非 articulation stage 返回结构化错误。
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：56 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- `git diff --check`：通过。

## 已知限制

- 当前支持 fixed/revolute 子集；prismatic、continuous 推断和高级 joint schema 尚未映射。
- Mesh geometry 目前保留源 USD URI 和 Prim path，尚未生成逐 Link viewport/collision cache。
- 模型尚未写入项目资产缓存，也未通过 RPC 注入 TypeScript Editor Store。

## 下一步

接入正式 Import USD 项目流：复制外部源和依赖，写入 robotics/manifest/report 缓存，注册 robot asset，
并保证 Scene 保存重开后保留 RoboticsModel；继续保持 object Mesh 导入兼容。
