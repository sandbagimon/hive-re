# Photoreal Obstacle Assets

日期：2026-08-10  
分支：`feature/drone-obstacle-avoidance`

## 目标

将无人机避障场景中的程序化方块升级为可分发的高清 PBR 实景模型，并引入摄影 HDRI 照明；物理
后端、占用地图和实时控制器继续使用稳定、低成本的简化碰撞体。

## 资产选择

- Poly Haven `Concrete Road Barrier 02`：CC0，2K glTF Web 版本，约 23.8K 三角面；模型位于
  中央 actor 下半部，上半部用金属施工围栏明确表达原 2.4 m 高的保守碰撞边界。这样避免不真实地
  竖直堆叠 Jersey barrier，也保持原控制轨迹、距离传感器命中和任务完成时序。
- Poly Haven `Barrel 03`：CC0，2K glTF Web 版本，约 1.5K 三角面；按每个 pillar 的尺寸堆叠，
  用较低面数补足工业细节。
- Poly Haven `Abandoned Hopper Terminal 03`：CC0，1K Radiance HDR；仅用于 image-based
  lighting 和反射，不作为场景几何背景。

所有网络文件均按 Poly Haven API 提供的 MD5 校验，来源、作者与校验值随资产保存。选择 2K 而
非 8K，是因为目标为远程开发环境中的实时 Web 视口；当前整套新增模型、贴图与 HDRI 约 14 MB，视觉
收益明显且不会让首次加载膨胀到数百 MB。HDRI 从初始 2K 验证版降为 1K；作为 roughness 较高
表面的 PMREM 输入几乎没有可见差异，但下载量由 6.3 MB 降至 1.6 MB。

## 实现

- 引入与现有 Three.js r160 精确匹配的官方 `GLTFLoader`、`RGBELoader` 和
  `BufferGeometryUtils`，沿用仓库内 Three.js MIT 许可文件；两个加载器按需动态导入，不增加
  首屏主包的解析成本。
- `ActorProperties.visual_model` 声明 URL、来源、许可、作者、分辨率和多个拟合实例。场景 JSON
  不包含渲染器对象，也不要求后端解析 glTF。
- `pbr-model-loader.ts` 缓存 glTF 模板，按 actor 克隆几何、材质和纹理资源，将 Y-up 模型旋转到
  SimLab Z-up 坐标，并按 collision proxy 的目标包围盒拟合。
- primitive proxy 保持可 raycast、可变换和可显示 collider debug，但正常渲染时关闭 color/depth
  write；glTF 失败时恢复 proxy 和程序化 PBR detail。
- 摄影 HDRI 异步替换程序化 PMREM；失败时继续使用无需网络的程序化日光环境。

## 验收

- TypeScript、前端模块测试和生产构建通过。
- Python 场景测试断言四个障碍的模型来源、CC0 许可、实例数量和视觉尺寸，同时验证实时避障任务
  物理结果不变。
- Chromium E2E 已两次等待 `photorealObstacleStatus=loaded` 与
  `photographicEnvironment=loaded`，截图检查 PBR 路障、钢桶、环境反射和软阴影，并完成真实在线
  重规划与落货。最终增加的金属围栏补全通过 TypeScript、production build 和 MuJoCo 完整任务
  回归；对应浏览器用例已保留相同资源断言和近景截图，供具备本地端口权限的环境复跑。

## 边界

- 高清模型是视觉 LOD，不进入 MJCF；传感器仍命中简化碰撞体，这是为可重复仿真与实时性能做的
  明确分层。
- 目前按目标包围盒做非均匀拟合，适合静态障碍。后续通用资产导入应支持作者提供的视觉锚点、
  单位和多级 collision proxy。
