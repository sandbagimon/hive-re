# Physical Drone Payload Delivery

日期：2026-08-05  
提交：待提交

## 目标

把“无人机从 A 点拿起物品并飞到 B 点”从视觉演示升级为可验证的真实 MuJoCo 仿真闭环。

## 主要改动

- Scene 增加 engine-neutral `attachments` 与 `delivery_tasks` 契约，并同步 JSON Schema。
- MJCF 支持初始关闭的 site-to-site connect/weld equality、局部锚点和接触探针表达动态挂载。
- 运行时只有在请求、距离、相对速度、持续时间和可选真实接触全部满足后才激活连接；支持即时释放
  和 Reset 初态恢复。
- Controller observation/action 增加 attachment 状态与命令；REST、应用 Bridge、资源管理器和
  WebSocket state 全链路使用稳定 ID。
- 配送任务以真实 payload 位姿和速度判断 waiting/in_transit/released/settling/completed，不由
  Controller 自报成功。
- 新增 Iris 配送场景和 cascaded position/velocity + attitude controller，包含实际机架 mixer、
  payload mass feed-forward、平滑五次轨迹与 0.15/-0.10 m/s MuJoCo wind。
- 配送资产升级为 36×28×22 cm、0.35 kg 的瓦楞纸箱，外观包含胶带、捆扎带、运单条码、
  接缝和护角，物理碰撞仍使用稳定箱体。
- 抓手升级为承力板、安装杆和四个独立 MuJoCo 接触吸盘，连续密封成功后使用 weld 锁定姿态；
  three.js 同步显示四吸盘、状态灯、连接线、锚点和任务状态。
- OpenUSD 无界关节的 `±Infinity` 统一归一化为 JSON `null`，场景与 robotics cache 使用严格 JSON，
  修复 Python 可读但浏览器 Open 失败的问题。

## 验证

- 模型、MJCF、接触门控、连接/释放、REST 路由和严格 JSON 回归测试通过。
- 30 秒、15000 个固定物理步完成起飞、接触抓取、带载飞行、B 点释放和稳定判定。
- Chromium 跨端口流程真实打开场景、上传 Controller、Run、WebSocket 推进并在约 41 秒内达到
  `task completed`；货物最终位置在 `[4.0, 3.0, 0.16]` 容差内。
- Python 全量 `265 passed, 3 skipped`；Chromium 全量 `17 passed`。
- Ruff、Mypy、TypeScript 类型检查、前端模块测试和 Vite production build 通过。

## 已知限制

- 当前四吸盘使用接触门控后的刚性 weld，不模拟真空压力、泄漏、吸盘变形或连接破坏。
- 电机一阶响应、桨叶入流、地效、电池模型和详细机身阻力仍未建模。
- 配送 Controller 按当前 Iris 与 0.35 kg 货物调参；资产质量或 rotor layout 改变后需重新标定。

## 下一步

- 将 pickup/dropoff 航点和 payload profile 参数化，避免示例 Controller 硬编码场景 ID。
- 增加绳索/多点挂载和载荷摆动控制。
- 为配送任务增加超时、失败原因、轨迹指标与 Gymnasium reward/termination adapter。
