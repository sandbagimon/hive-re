# Real-time Drone Replanning

日期：2026-08-10
分支：`feature/drone-obstacle-avoidance`

## 问题

原避障示例只在 Controller 初始化时根据已知矩形障碍运行一次 A*。运行阶段的 rangefinder 仅参与
局部排斥，未知障碍不会更新全局路线，因此属于“静态全局路线 + 实时局部避障”。

## 本次改造

- 新增通用 `GridSpec`、`LiveOccupancyGrid` 和 `IncrementalAStarPlanner`。
- 12 路 rangefinder 以 `50 Hz` 更新二维占用栅格；射线提供空闲证据，命中提供占用证据，未知
  障碍观测使用 `2 s` TTL，允许移动障碍离开后释放栅格。
- 当前路线被占用或 `1.5 s` 无有效进展时，从无人机实时位置触发重规划。
- 每个 `500 Hz` 控制回调最多扩展 48 个 A* 节点，把规划分摊到多个物理帧，不阻塞飞控截止时间。
- 规划期间安全悬停；无路线时进入 `blocked`，以 `0.5 s` 周期重试，而不是继续向障碍物飞行。
- `ControllerAction.navigation` 和 `SimulationState.navigation` 发布路线、路线/地图版本、状态、
  重规划次数、占用格数量及错误信息。
- three.js 根据最新运行路线实时更新：following 为青色、planning 为黄色、blocked 为红色、
  complete 为绿色；HUD 显示导航状态与重规划次数。
- 示例增加不在先验地图中的紫色柱体，强制演示传感器发现、路线失效和在线重规划。

## 验证

- 占用地图命中、TTL 过期、路径失效和分帧增量 A* 单元测试。
- Controller 合成观测测试确认 `planning -> following`、路线版本增加且新路线避开实时占用格。
- MuJoCo 21,000-step 物理闭环确认发生至少一次重规划，且货物最终稳定投递到 B 点。
- 浏览器隔离部署测试确认 Controller 加载、在线重规划、WebSocket 状态和 Three.js 路线版本更新。
- 原有 Controller runtime、SimulationSession、前端构建和静态场景路径测试保持通过。
- 完整 Python 回归：`285 passed, 3 skipped`；前端单元测试、TypeScript、Vite production build、
  实时重规划浏览器测试和原有 A→B 浏览器测试全部通过。

## 当前边界

- 在线地图是二维局部占用栅格，不包含 SLAM 定位或三维点云。
- 观测采用 TTL 处理移动障碍，尚未估计速度或预测未来轨迹。
- 先验静态地图仍属于任务 Controller 配置；通用 engine-neutral map/collision-query 服务尚未交付。

后续画面与任务标识改进见
[`2026-08-10-drone-scene-visual-upgrade.md`](2026-08-10-drone-scene-visual-upgrade.md)。
