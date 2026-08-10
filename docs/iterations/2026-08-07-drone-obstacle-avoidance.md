# Drone Obstacle-Aware Delivery

> 2026-08-10 后续迭代已加入在线占用地图和实时增量重规划，参见
> [`2026-08-10-realtime-drone-replanning.md`](2026-08-10-realtime-drone-replanning.md)。

日期：2026-08-07
分支：`feature/drone-obstacle-avoidance`

## 目标

在既有 Iris 物理运货闭环上增加真实距离感知、全局规划和局部避障，保持前端、控制器契约和
MuJoCo 适配器解耦，并交付可从浏览器运行的完整示例。

## 主要改动

- 新增引擎无关 `rangefinder` schema、最大量程、固定频率、确定性噪声、运行状态和 Controller
  Observation。
- MJCF 导出 link-mounted site 与原生 MuJoCo rangefinder；运行时映射稳定 sensor ID，不暴露
  引擎索引。
- JSON/CSV Recording 增加 rangefinder typed event。
- 新增 12 路、4 m、50 Hz Iris 水平测距环和含中央高墙的物理配送场景。
- 新增 A* 障碍膨胀/路线简化、rangefinder 局部排斥与沿墙保护、原有物理抓取/释放状态机。
- 前端 Sensor Inspector 显示 distance/hit，视口绘制 A* 路线并实时显示按安全距离着色的射线，
  HUD 显示最近 clearance。
- 将 Controller 初始化和逐帧实时控制的截止时间分离，避免 A* 初始化在服务器瞬时负载下被误判
  为逐帧超时；浏览器回归覆盖加载、12 路测距和起飞运行状态。
- 将 Iris 运货基础控制器提升到 `simlab.controllers`，消除上传脚本对仓库 `examples` 包的隐式
  依赖，确保隔离项目与安装部署环境可加载。

## 验证

- 距离传感器模型、频率、噪声重放、schema、不可变 Controller Observation 和 Recording 测试。
- 障碍配送端到端 MuJoCo 测试：15,000 physics steps 内任务 `completed`，局部避障触发，最小
  测距大于 `0.35 m`，货物落在 B 点容差内。
- Python lint、TypeScript typecheck、frontend unit/build 验证。
- 浏览器隔离部署回归通过：避障 Controller 加载后为 `ready`，运行后保持 `active` 并完成起飞；
  原有无障碍 A→B 浏览器运货验收继续通过。

## 已知限制

- A* 使用任务配置的静态矩形地图，尚未自动从所有 scene collider 建立 occupancy map。
- 水平二维射线不提供三维点云、动态障碍跟踪或 SLAM。
- 控制器状态机阶段与规划指标尚未作为独立 telemetry schema 推送到 UI。

## 下一步

- 增加引擎无关 collision-query/map resource，让规划器无需复制场景障碍参数。
- 增加动态障碍速度估计、重规划、blocked/timeout/emergency-hover 任务状态。
- 将 rangefinder observation 纳入 Gymnasium/gRPC algorithm data plane。
