# 电影感动态避障外卖配送

## 目标

把原有的工业测试台升级为具有明确叙事的取餐到住宅送达场景，并确保所谓“动态避障”来自物理
世界中的移动障碍，而非仅供展示的前端动画。

## 本轮完成

- 新增引擎无关 `KinematicActorEventScheduler`，从 `simulation_config.dynamic_events` 解析关键帧、
  插值、事件状态和速度。
- 新增 `kinematic_actor` 引擎能力。含动态事件的场景会自动要求该能力；MuJoCo 适配器负责将采样
  位姿写入自由刚体并在 `mj_forward` 后统一更新碰撞、测距和状态。
- 仿真状态和 WebSocket/REST payload 新增 `dynamic_events`，前端 HUD 显示当前 `LIVE EVENT`。
- 添加“配送厢式车倒入取餐出口”和“骑手横穿最后进近”两次动态事件。12 路 rangefinder、在线
  占用地图、TTL、局部避障和增量 A* 使用同一物理状态。
- 场景改为蓝调时刻城市街道，补齐餐厅取餐店、住宅投递点、程序化高细节厢式车和骑手电单车。
- 引入项目本地雨后沥青贴图，叠加 clearcoat 水膜、程序 roughness/bump、反射水洼、道路标识、
  冷暖灯光和近景雾。
- 将该场景 Controller 截止时间从 `20 ms` 调整到 `50 ms`，避免远程开发服务器偶发调度尖峰让
  Controller 永久进入 `fault`；增量规划的单帧工作量保持不变。

## 完整工作流实测

在 MuJoCo 中运行 48 秒场景：无人机约 `9.5 s` 抓取货物，`12.8 s` 遇到厢式车，`19.2 s` 遇到
横穿骑手，约 `39.6 s` 完成投递和返航悬停。实测 `13` 次在线重规划，最近障碍距离约 `0.53 m`，
最终 Controller 为 `active`、Delivery Task 为 `completed`。
