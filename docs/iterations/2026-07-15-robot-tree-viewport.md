# Robot Tree and Viewport

日期：2026-07-15
提交：待提交

## 目标

让正式 Import USD 写入 Scene 的外部机器人结构在编辑器中可见，同时保持 actor authoring transform、
history 和普通 object 渲染行为不变。

## 主要改动

- 补充 TypeScript RoboticsModel、Articulation、Link、Joint、Actuator、Sensor 和 visual/collider 类型。
- Scene Tree 在 robot actor 下显示 Link 与 Joint 子项；子项使用 stable ID 作为 title，不改变 actor
  selection 所有权。
- three.js viewport 为 articulation root 和每个 Link 建立 Group 层级，应用 local position/quaternion。
- 渲染 Box、Sphere、Ellipsoid、Cylinder/Capsule 的逐 Link VisualGeometry，应用颜色和基础 PBR 参数。
- robot actor transform 作用于 articulation root，TransformControls 仍只修改 actor authoring transform。
- raycast 改为递归命中机器人子 Mesh，并回到所属 actor selection；selection emissive 支持 Group。
- 删除 robot actor 时同步清理对应 articulation，且整个操作仍可 undo/redo。
- checked-in generated JavaScript 与 TypeScript 源同步更新。

## 验证

- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：60 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- `git diff --check`：通过。
- Python 资产测试确认 TS 源包含 robot hierarchy、visual geometry 和 viewport builder。
- 当前环境没有 Node.js/npm，不能运行 TypeScript typecheck、frontend Store test 或浏览器截图验收。

## 已知限制

- Link/Joint 子项当前为只读层级，不支持独立 selection 或 inspector。
- Mesh VisualGeometry 尚未生成逐 Link BufferGeometry cache，当前完整显示 primitive visual 子集。
- Collider debug overlay 尚未覆盖机器人 Collider。
- 未经真实 QWebEngine 截图验证，需在具备 Node.js 和显示服务的环境补跑。

## 下一步

扩展 MJCF exporter，把 Articulation/Link/Joint/Collider/Inertial/Actuator 转成 MuJoCo 模型，并用外部
机械臂 fixture 做编译和物理结构验收。
