# Robotics Intermediate Model

日期：2026-07-15
提交：待提交

## 目标

建立外部 OpenUSD、MJCF、MuJoCo runtime 和 TypeScript editor 后续共同复用的版本化机器人中间模型，
不在 importer、exporter 或 UI 中引入格式专用的临时结构。

## 主要改动

- 新增 `shared/schemas/robotics.schema.json`，覆盖 Articulation、Link、Joint、Actuator、Sensor、
  VisualGeometry、Collider 和 Inertial。
- 新增 Python dataclass 与 JSON 序列化/反序列化，刚体局部变换使用 xyzw quaternion。
- 新增 Draft 2020-12 Schema 校验和跨引用语义校验，错误包含稳定 code、JSON path 和 message。
- 校验重复 ID、link hierarchy、joint parent/child、非零 axis、joint/control range、initial position，
  以及 actuator/sensor 悬空引用。
- Scene 增加可选 `robotics` 字段；旧 scene 缺少该字段时加载和再次序列化保持兼容。
- schema 作为安装数据发布，并加入 `jsonschema` 运行时依赖。
- 新增 canonical two-joint arm JSON fixture，表达 fixed base、三个 link、两个 revolute joint、两个
  position actuator 和一个 joint sensor。

## 验证

- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：47 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- `git diff --check`：通过。
- 当前环境没有 `npm` 可执行文件，未运行 `npm run typecheck` 和 `npm run test:frontend`；本轮没有
  修改 TypeScript。
- 不设置 `QT_QPA_PLATFORM=offscreen` 时，Qt 测试因当前会话无 display/xcb 而进程 abort。

## 已知限制

- 该提交只建立中间模型，不读取 OpenUSD articulation，也不导出机器人 MJCF。
- TypeScript robotics 类型和编辑器层级将在 importer 返回结构稳定后接入。
- JSON fixture 用于模型测试，不替代外部 USD 文件的产品验收。

## 下一步

实现 `ImportIssue`/`ImportReport`、OpenUSD stage loader 和许可证明确的外部 USD 机械臂 fixture；从
磁盘走公开导入路径，诊断缺失 reference/payload/mesh 依赖，并保持现有单 Mesh 导入 API 兼容。
