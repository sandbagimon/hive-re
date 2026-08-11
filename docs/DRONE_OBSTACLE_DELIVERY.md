# 无人机避障运货示例

SimLab 提供了一个可直接运行的 Iris 四旋翼实时避障外卖配送闭环。蓝调时刻的无人机从临街餐厅
取餐，通过先验地图、12 路 MuJoCo 距离传感器构建的在线占用栅格和增量 A* 飞往住宅投递点，
抵达后释放外卖袋并悬停。
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

场景为逐帧控制保留 `50 ms` 截止时间，并为包含 A* 规划的 Controller `reset()` 单独提供
`200 ms` 初始化预算；初始化时的路径规划不会再因瞬时服务器负载误触发逐帧超时。
通用的 Iris 抓取、轨迹和飞控逻辑位于 `simlab.controllers.iris_payload_delivery`，上传的避障
Controller 不依赖仓库内的 `examples` Python 包，因此在远程服务器和隔离项目目录中也能加载。

预期过程是预转、起飞、在 **NIGHT KITCHEN** 取餐点抓取外卖袋并负载爬升。约 `12.8 s`，一辆
未录入先验地图的配送厢式车倒入出餐通道并短暂停留；约 `19.2 s`，另一名骑手进入最后进近
航路。二者都不是 three.js 动画，而是由引擎无关的 `dynamic_events` 关键帧驱动 MuJoCo 自由刚体，
因此会同时进入碰撞、rangefinder 和 Controller Observation。无人机发现当前路线失效后悬停、
增量重规划并绕行，最终在住宅 B 点下降释放。HUD 最终显示 `task completed`。
视口路线在跟随时为青色、规划时为黄色、阻塞时为红色、完成时为绿色；HUD 显示最近障碍距离、
导航状态、重规划次数和当前 `LIVE EVENT`。选择 Scene Tree 下的任一 Range Sensor，可在
Inspector 查看实时距离、命中状态、时间戳和序列号。

示例的 `visual_style` 只决定 three.js 表现，物理尺寸仍由 primitive collider 决定。街面使用项目内
的高清雨后沥青 base-color、程序 roughness/bump、clearcoat 水膜和局部反射水洼；取餐点包含发光
招牌、玻璃门窗、室内暖光与遮雨棚，住宅点包含窗灯、阳台、入口雨棚和地址牌。动态厢式车具有
车漆 clearcoat、玻璃、轮胎、灯组与侧面标识，骑手具有电单车、头盔和外卖箱。静态施工障碍继续
使用 Poly Haven CC0 的 2K glTF/PBR 风化路障和锈蚀钢桶；透明 primitive proxy 负责选择、碰撞
调试和 MuJoCo 物理。模型加载失败时会退回程序化障碍，不会产生不可见碰撞体。

编辑器使用 Poly Haven `Abandoned Hopper Terminal 03` 的 1K 摄影 HDRI 提供真实环境漫射和
反射，并为本场景启用蓝调时刻天空、冷色环境填充、暖色主光、餐厅/住宅 practical lights、
低曝光 ACES tone mapping、柔和阴影和近景雾。实时路线仍使用立体线段和脉冲航点。OpenUSD
资产的作者态 PBR 贴图继续优先，不会被 primitive 材质覆盖。资产来源、作者、许可和校验值记录在
[`frontend/public/models/polyhaven/README.md`](../frontend/public/models/polyhaven/README.md)
以及
[`frontend/public/environments/polyhaven/README.md`](../frontend/public/environments/polyhaven/README.md)。

## 控制链路

```text
dynamic_events -> 物理刚体位姿 -> MuJoCo 碰撞/射线
                                      ↓
先验地图 -----------------------> 融合占用栅格
                                    ↑
MuJoCo rangefinder 50 Hz -> 射线清空/命中/TTL
                                    ↓
                     路径失效或停滞检测
                                    ↓
                 分帧增量 A* -> 原子替换路线 -> WebSocket/three.js
                                    ↓
            局部排斥/安全悬停 -> 500 Hz 飞控 -> rotor mixer -> MuJoCo
```

- 动态事件由 scene.json 声明 actor、激活/完成时间和关键帧；运行时调度器负责插值，引擎适配器
  只负责应用位姿。带事件的场景自动要求 `kinematic_actor` 能力，未来 Newton 适配器若未实现会在
  preflight 明确拒绝，而不是静默忽略移动障碍。
- 地图层每 `20 ms` 融合一轮测距：射线穿过的格子标记为空闲，命中点进入临时占用层；观测超过
  `2 s` 未再次出现会过期，因此移动障碍离开后能够释放原区域。先验障碍和实时命中都按
  `0.68 m` 的负载安全半径膨胀。
- 路径被新占用格阻断或 `1.5 s` 没有取得有效进展时触发重规划。A* 每个控制帧最多扩展 48 个
  节点，不会一次占满 500 Hz 控制回调；规划期间无人机保持当前位置，无路可走时进入 `blocked`
  悬停并每 `0.5 s` 重试。
- 新路线通过 `ControllerAction.navigation` 原子写入运行状态，包含路线/地图版本、重规划次数和
  状态，并经 REST/WebSocket 推送到前端。
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

自动化测试验证：直达线被膨胀后的高墙阻挡；厢式车和骑手按关键帧真正移动且状态经 API 发布；
rangefinder 观测使当前路线失效；A* 在多个控制帧中完成重规划；路线版本和重规划计数增加；
前端收到并显示新路线与动态事件；局部避障实际触发；货物最终在 B 点稳定，任务状态为
`completed`。

当前是水平二维在线占用地图，不是完整 SLAM：没有定位漂移估计、障碍速度预测、三维点云或跨任务
持久地图。已知静态障碍仍由任务配置提供，未知/移动障碍由 rangefinder 在线补充。下一步可将
occupancy map/collision-query 提升为引擎无关服务，并接入扫描式 LiDAR 和动态障碍轨迹预测。
