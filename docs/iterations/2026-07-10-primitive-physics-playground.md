# Primitive Physics Playground

日期：2026-07-10

## 目标

推进 M5 的第一小步：先让 primitive scene 能产生更直观的 MuJoCo 物理效果，而不是直接跳到完整机器人或高级物理参数编辑。

## 主要改动

- 扩展 `assets/metadata.json`：
  - Box/Sphere/Cylinder 默认 dynamic。
  - 新增 Ground。
  - 新增 Table。
  - 新增 Ramp。
  - 为 primitive asset 增加基础 `physics.dynamic`、`physics.mass`、`physics.friction`。
- 主窗口添加 asset 时支持读取 `default_transform`。
- Property Panel 新增基础物理编辑：
  - Dynamic。
  - Mass。
  - Friction。
- MJCF exporter 支持 static/dynamic primitive：
  - dynamic actor 导出为 body + freejoint + geom。
  - static actor 导出为 fixed world geom。
  - 支持 plane geom。
  - 导出 mass/friction。
- three.js viewport 支持 plane/ground 显示。
- 更新 `examples/demo_project/scene.json` 为 Physics Playground：
  - Ground。
  - Ramp。
  - Sphere。
- 新增 asset metadata 和 static/dynamic MJCF export 测试。
- 更新 README 和产品计划。

## 验证

- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m pytest`：`15 passed`。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m ruff check .`：通过。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m compileall -q src tests`：通过。
- `examples/demo_project/scene.json` 已通过 `python -m json.tool` 校验。

## 已知限制

- 只支持 very basic physics properties：dynamic、mass、friction。
- 还没有 restitution/contact/solver/timestep/gravity UI。
- Static actor 现在导出为 world geom，不会回传 simulation state。
- Property Panel 的 physics controls 仍是通用控件，尚未按 actor/geom 类型做 typed inspector。

## 下一步

- 增加 physics validation preflight。
- 加入 restitution/contact 参数。
- 给 simulation controls 增加 speed/timestep/gravity 反馈。
- 再推进 M2 的 duplicate actor 和 Scene Tree context menu。
