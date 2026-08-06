# Houhai Daylight Visual Style

日期：2026-08-04  
提交：待提交

## 目标

消除深圳后海 2 km 城市场景的统一灰白“白模感”，在不增加 MuJoCo 物理复杂度的前提下，提供
清晰、有层次且适合无人机仿真的日间城市视觉效果。

## 主要改动

- 建筑根据 Overture `class`、`subtype`、高度和稳定 ID 分配到 13 个确定性样式，不同机器重建
  得到相同颜色。
- 每个建筑样式分别聚合立面与屋顶，最终保持 103 个 USD 视觉 mesh，而不是为 2,703 栋建筑
  创建数千个独立 draw call。
- 道路按 arterial、collector、local、pedestrian 分类着色；主干道与次干道生成视觉中心线。
- 水面、道路和中心线只进入视觉缓存；地面与建筑外壳继续作为 dedicated collision。
- Three.js 在检测到公里级环境时自动启用 ACES 色调映射、sRGB 输出、日间渐变天空、暖色主光、
  冷色补光，并隐藏编辑网格和坐标轴；普通米级编辑场景继续使用原有深色环境。
- 保留稳定的 catalog ID `openusd_houhai_2km_b463d22fff` 以兼容旧场景，同时把视觉、碰撞与
  source 引用更新到新的内容寻址缓存 `openusd_houhai_2km_7e5a5eb3ce`；资产库仍只显示一个
  `Shenzhen Houhai 2km` 条目。

## 验证

- 视觉缓存：187,391 vertices、74,779 triangles、33 种顶点颜色。
- 碰撞缓存保持：112,445 vertices、49,797 triangles，不包含道路、水面和中心线。
- MuJoCo：`nmesh=1`、`ngeom=1`，模型编译成功并推进至 `0.01 s`。
- TypeScript 类型检查、前端模块测试与 Vite 生产构建通过。
- Playwright 在真实 Chromium 中加载资产，确认 `data-environment-mode="city"`、只请求一次视觉
  缓存，并生成 Viewport 截图。

## 已知限制

- 当前属于风格化 LoD1 日间城市，并非照片级重建；没有真实建筑立面贴图和地标建筑细节。
- 简化中心线用于增强远距离道路识别，不代表精确车道级地图。

## 下一步

- 若任务需要近距离飞行，可增加基于共享纹理图集的程序化窗格、屋顶设备和实例化树木。
- 若任务需要测绘级真实性，应接入合法授权的摄影测量/倾斜摄影数据，并配套 tile streaming 与 LOD。
