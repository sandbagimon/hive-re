# OpenUSD Asset Import

日期：2026-07-10

## 目标

- 从编辑器直接导入 `.usd`、`.usda`、`.usdc` 和 `.usdz`。
- 在 three.js viewport 显示导入网格。
- 用现有 Inspector 编辑 dynamic、material、mass/density 和 friction。
- 将导入资产转换为 MJCF mesh geom，并由 MuJoCo 编译和运行。

## 实现

- 新增 `OpenUsdImportService`，使用官方 OpenUSD Python bindings 遍历 Stage。
- 应用 Stage transform、`metersPerUnit` 和 up-axis 转换。
- 将可见 `UsdGeomMesh` 三角化并合并为一个 Actor。
- 在 `assets/imported/<asset-id>/` 生成 source、`manifest.json`、`visual.json` 和 `collision.obj`。
- 从 `UsdPhysics` 属性读取 rigid-body、mass/density、friction 和 restitution metadata。
- 新增 `importOpenUsd`、`getVisualGeometry` Bridge RPC。
- Viewport 异步加载缓存 BufferGeometry。
- MJCF exporter 为导入 Actor 生成 `<asset><mesh>` 和 `<geom type="mesh">`。
- Preflight 校验缓存路径和碰撞网格，并让 MuJoCo 编译最终 MJCF。

## 第一版边界

- 一个 USD Stage 作为一个刚体 Actor 导入。
- 多刚体 Stage 会给出 warning，并暂时合并。
- 碰撞体暂时使用合并后的视觉网格。
- 支持 `displayColor`，尚未完整支持 `UsdPreviewSurface`、纹理和动画。
- 默认仿真链路是 OpenUSD -> SimLab Schema/cache -> MJCF -> MuJoCo，不依赖实验性的 MuJoCo native USD decoder。
- `usd-core` 依赖和 TOST license 已记录在 `docs/THIRD_PARTY_NOTICES.md`。

## 后续

- 保留 USD hierarchy，并映射 Robot/Link/Joint/Actuator。
- 识别专用 collision prim 和 collision approximation。
- 复制和重写外部 USD/texture dependencies。
- 增加 PBR material、texture 和 articulation fixtures。
