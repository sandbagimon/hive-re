# Drone Scene Visual Upgrade

日期：2026-08-10
分支：`feature/drone-obstacle-avoidance`

## 目标

在不改变 MuJoCo 几何、碰撞和实时避障逻辑的前提下，提高无人机运货示例在 three.js 视口中的
空间层次、任务可读性和运行状态辨识度。

## 实现

- 普通编辑场景增加程序化天空、作业地面和 equirectangular 日光环境；Three.js 将环境处理成
  PMREM，为金属、清漆和粗糙表面提供一致的 image-based lighting，不依赖外部 HDRI 文件。
- 开启 2048 分辨率 PCF soft shadow；普通场景根据 actor bounds 调整阴影视锥，大型城市资产继续
  禁用实时阴影以控制开销。
- `operations_ground` 使用确定性程序纹理；`landing_pad_pickup` 和
  `landing_pad_dropoff` 显示带 A/B 与 PICKUP/DROPOFF 字样的起降标识。
- 已知墙体、未建图柱体和安全柱通过不同灯带与信标区分；这些 detail 只是 child mesh，不进入
  Scene actor、MJCF 或碰撞模型。
- 新增独立 `procedural-materials.ts`：为混凝土、纸板、粉末喷涂和环氧涂层确定性生成 base-color
  modulation、bump 与 roughness maps；起降坪和涂装 primitive 使用 `MeshPhysicalMaterial` 的
  clearcoat/sheen，OpenUSD mesh 继续使用作者态 base-color/normal/roughness/metalness 贴图。
- 导航路线增加立体线段和脉冲航点，仍由 runtime navigation status 控制颜色。
- Frame All 忽略纯背景作业地面，并在打开多 actor 场景时自动构图；任务区域不再因大地面而缩成
  视口中央的一小块。
- HUD 和工具栏使用半透明层次、柔和描边与内阴影，视口边缘增加轻微 vignette。

外卖袋的后续高保真替换见
[`2026-08-10-insulated-takeout-bag.md`](2026-08-10-insulated-takeout-bag.md)。
障碍物实景扫描模型与摄影 HDRI 的后续升级见
[`2026-08-10-photoreal-obstacle-assets.md`](2026-08-10-photoreal-obstacle-assets.md)。

## 验证

- TypeScript 类型检查、前端模块测试和 Vite production build 通过。
- Chromium E2E 打开真实 obstacle delivery scene，断言 enhanced render 和 soft shadow 模式，
  截图检查 A/B 标识、障碍灯带、阴影、路线与构图，并完成一次在线重规划。
- 完整 Python 回归：`285 passed, 3 skipped`；无人机抓取、避障、重规划和落货结果不变。

## 边界

- 本轮最初的 IBL 来自程序化日光环境；后续已升级为摄影 HDRI，并保留程序环境作为离线回退。
- 阴影属于视觉效果，不反馈给物理引擎或传感器。
- 大型城市环境仍采用无实时阴影的 daylight 模式；后续可按视锥和层级引入 cascaded shadow map。
