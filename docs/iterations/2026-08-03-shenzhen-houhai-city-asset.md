# Shenzhen Houhai 2 km City Asset

日期：2026-08-03  
提交：待提交

## 目标

为无人机和城市环境仿真提供一个以深圳南山后海为中心、范围约 2 km × 2 km、能够由当前
Three.js/OpenUSD/MuJoCo 管线直接使用的 LoD1 城市场景。

## 主要改动

- 以 WGS84 `113.919790, 22.526595` 为中心建立精确的 2,000 m 方形范围。
- 从 Overture Maps `2026-07-22.0` 建筑主题裁剪 2,703 个建筑 footprint；通过空间索引和
  HTTP Range 仅读取一个相交 Parquet 行组。
- 从 OpenStreetMap Overpass 获取 949 个道路 way 和水体数据，生成 953 个道路表面和 8 个
  水面。
- 新增 `scripts/build_houhai_usd.py`，可从缓存 GeoJSON 重建二进制 OpenUSD；模型按四个建筑
  tile 组织，并以本地 ENU 近似平面坐标将中心设置为原点。
- 明确拆分视觉和碰撞：道路、水面仅参与渲染，地面和建筑应用 `UsdPhysics.CollisionAPI`。
- 将生成资产注册为 `Shenzhen Houhai 2km`，并记录来源、范围、许可、数据快照和高度推断策略。
- 新增 `geospatial` 可选依赖组，不把 PyArrow/Shapely 等大型 GIS 构建依赖加入正式后端运行时。
- 修复 kilometre-scale 场景的可读性：带顶点颜色的缓存模型不再与 Actor fallback color 二次相乘；
  相机取景后按包围球动态设置 near/far、Fog 和 Grid，并在新增大型环境资产时自动进行等距视角
  取景，不改变普通米级物体和机器人的既有相机交互。
- 新增 `Houhai daylight` 视觉主题：按建筑类别和高度确定性分配 13 组立面/屋顶样式，道路分为
  arterial、collector、local、pedestrian 四级，并加入主干道中心线、水面强调色与日间天空环境。

## 验证

- OpenUSD Stage：Z-up、米制、默认 Prim `/Houhai`；视觉模型 187,391 vertices、74,779 triangles、
  103 个有界语义 mesh、33 种最终顶点颜色。
- OpenUSD importer：生成 dedicated collision，碰撞模型 112,445 vertices、49,797 triangles。
- WebApplication 资产列表与 `getVisualGeometry` 成功读取新资产。
- Chromium 验证新增后海资产后自动进入 `city` 环境、取景半径超过 1 km、Fog 起点位于完整
  模型之后，且视觉缓存只请求一次。
- 真实 MuJoCo：MJCF 编译约 0.59 秒，`nmesh=1`、`ngeom=1`，`mj_step` 成功推进至 `0.01 s`。
- 资产 metadata 与 OpenUSD importer 聚焦测试通过。

## 已知限制

- 只有 18 个建筑带显式高度、287 个带楼层数；其余 2,398 个使用 9/12/18/24 m footprint
  面积启发式，因此属于 LoD1 近似模型，不是测绘级数字孪生。
- 尚未包含真实立面纹理、屋顶细节、树木、路灯、完整车道标线和地形高程。
- 当前碰撞包含全部建筑外壳，适合无人机环境和静态碰撞，但后续大规模训练应继续生成更轻量的
  分块 box/convex proxy。

## 下一步

- 接入获得授权的建筑高度栅格或 GlobalBuildingAtlas 高度数据，并评估非商业许可限制。
- 增加按需 tile streaming、视锥裁剪和距离 LOD。
- 为无人机任务标注起降点、禁飞区、航路和城市风场。
