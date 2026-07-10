# Visual Physics Fidelity

日期：2026-07-10

## 目标

让 viewport 中可见的 primitive geometry、transform 和材质意图，与 MuJoCo 使用的 collider 和动力学参数保持一致。

## 已完成

- 建立 primitive geometry contract：
  - Box 使用 half extents。
  - Sphere 使用 radius。
  - Cylinder 使用 radius/half-height，局部轴为 Z。
  - scene rotation 为 three.js XYZ radians。
  - scale 在 MJCF 边界烘焙到 geom size。
- MJCF rotation 改为高精度 quaternion。
- 非均匀 Sphere scale 导出为 Ellipsoid。
- Cylinder 要求 X/Y radial scale 一致。
- Cylinder viewport height 修正为两倍 half-height。
- 删除 exporter 隐式 ground。
- Ground 改为位于 Z=0 下方的有限静态 Box。
- Collider Debug Overlay：
  - Dynamic 橙色 wireframe。
  - Static 青色 wireframe。
  - 黄色 center-of-mass marker。
  - 工具栏按钮和 `C` 快捷键。
- 增加 Default、Rubber、Wood、Metal、Ice material presets。
- 增加 Explicit Mass / Material Density 模式。
- Material preset 联动 density、friction、solref/solimp、roughness/metalness。
- geom name 统一使用稳定 actor id，便于 contact report 和调试。

## 自动验收

- JS viewport contract 与 Python contract 的 geom type/size 对齐。
- Python contract 与 MuJoCo model geom type/size 对齐。
- Actor position/quaternion 与 MuJoCo body/world geom pose 对齐。
- 导出 geom 数量等于 scene object actor 数量，不存在隐藏 collider。
- Physics Playground 球体先接触 Ramp，再接触 Ground，并沿坡面正确运动。

## 验证

- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m pytest`：`31 passed`。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m ruff check .`：通过。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m compileall -q src tests`：通过。
