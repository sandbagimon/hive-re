# 无人机避障运货示例

SimLab 提供了一个可直接运行的 Iris 四旋翼避障运货闭环。无人机从 A 点抓取真实动态货物，
通过 A* 全局路线和 12 路 MuJoCo 距离传感器绕过高墙，抵达 B 点后释放货物并悬停。
three.js 只显示仿真状态与射线，不参与物理或控制计算。

## 运行

在仓库根目录启动可信 Controller 模式：

```bash
./start_backend.sh --allow-controller-execution
```

另开终端启动前端：

```bash
./start_frontend.sh
```

打开 `http://127.0.0.1:5173`：

1. 点击 **Open**，选择 [`examples/drone_delivery_obstacles/scene.json`](../examples/drone_delivery_obstacles/scene.json)。
2. 在 Scene Tree 中选择 **Pegasus Iris Quadcopter**。
3. 在 Controller 面板加载 [`examples/controllers/iris_obstacle_delivery.py`](../examples/controllers/iris_obstacle_delivery.py)。
4. 点击 **Run**，可切换 `2x` 加速。

预期过程是预转、起飞、A 点抓取、负载爬升、绕过中央红色高墙、B 点下降释放、退离并悬停。
HUD 最终显示 `task completed`。视口用青色显示 A* 路线，射线按距离显示为绿色、黄色或红色；HUD 同时显示当前
最近障碍距离。选择 Scene Tree 下的任一 Range Sensor，可在 Inspector 查看实时距离、命中状态、
时间戳和序列号。

## 控制链路

```text
任务状态机 -> 膨胀障碍物地图 -> A* -> 平滑路线
                                      |
MuJoCo rangefinder -> 固定频率观测 -> 局部排斥/沿墙保护
                                      |
                         位置/姿态控制 -> rotor mixer -> MuJoCo
```

- 全局层在 `0.2 m` 栅格上规划，并按 `0.68 m` 的负载安全半径膨胀障碍物；之后用碰撞检查做
  line-of-sight 简化。路线不是人工编写的绕行 waypoint。
- 局部层直接读取 `ControllerObservation.rangefinders`。`1.2 m` 内开始施加排斥，正前方小于
  `0.9 m` 时采用确定性的顺时针沿墙速度；小于 `0.35 m` 时优先退离。
- 抓取仍由接触、锚点距离、相对速度和持续时间共同门控。货物质量进入推力前馈，释放后的任务
  完成条件仍由真实位置、速度和稳定时间决定。

## 距离传感器契约

`rangefinder` 是机器人中间模型的一等传感器，使用稳定 `link_id`、局部 xyzw 姿态、
`max_distance`、固定更新频率和可复现噪声。MuJoCo 导出器在 link 上创建 site，并沿 site 的
`+Z` 方向发射原生 rangefinder ray。无命中时返回最大量程且 `hit=false`；命中距离经过确定性
噪声后裁剪到 `[0, max_distance]`。

运行状态、WebSocket、Controller Observation、Inspector 和 JSON/CSV Recording 使用同一稳定 ID，
不向控制器暴露 MuJoCo sensor address。当前示例使用 12 路水平射线、`4 m` 量程、`50 Hz` 更新率和
`4 mm` 标准差白噪声；Reset 会重放相同噪声序列。

## 验收与边界

自动化测试验证：直达线被膨胀后的高墙阻挡、A* 每段均无碰撞、12 路传感器进入控制器、局部
避障实际触发、最小射线间距大于 `0.35 m`，并且货物最终在 B 点稳定、任务状态为 `completed`。

当前全局地图由任务 Controller 配置，尚未从任意 Scene 静态碰撞体自动建图；距离传感器可以对
未写入地图的障碍物做局部保护，但不等同于完整 SLAM。下一步若要支持任意场景，应把 occupancy
map/collision-query 作为引擎无关任务输入，并增加动态障碍预测与失败重规划。
