# 无人机公园蜂群配送（多机并行取送 + 避障）

BeeFoundrySim 提供了一个可直接运行的多无人机蜂群配送闭环：三台 Iris 四旋翼在完整的
Architectural Brownstone Park（Optimized 流式配置）中同时执行取货—巡航—投递任务。
每架无人机拥有独立的克隆 articulation（links/joints/actuators/rangefinders 全部
唯一命名）、独立载荷、真空吸盘 attachment 与配送任务；两台未录入先验地图的动态
障碍（清洁车、维修货车）会在任务中横穿飞行走廊，机载 12 路测距 + 在线占用栅格 +
增量 A* 重规划 + 反应式避障（含机间互斥）负责绕行。

## 运行

在仓库根目录启动可信 Controller 模式后端（需已解压 Brownstone 资产包，公园
Optimized 缓存就绪后资产面板显示 ready）：

```bash
./start_backend.sh --allow-controller-execution
./start_frontend.sh
```

打开 `http://127.0.0.1:5173`：

1. 点击 **Open**，选择 [`examples/drone_delivery_park/scene.json`](../examples/drone_delivery_park/scene.json)。
   视口通过 `stream_scene_id` 渐进加载公园分块；物理侧只包含隐形工作区地板、
   三个 2.3 m 公园构筑物碰撞盒与两个售货亭。
2. 在 Scene Tree 中选择任一 **Pegasus Iris** 机器人。
3. 在 Controller 面板加载 [`examples/controllers/iris_swarm_delivery.py`](../controllers/iris_swarm_delivery.py)。
4. 点击 **Run**；三机同时起飞，各自前往 pickup 点抓取保温袋，负载巡航并绕开
   先验障碍与动态障碍，最终在各自 dropoff 垫板释放。

## 架构

```text
scene.py: _clone_articulation(raw, suffix)
  深拷贝 Iris articulation 并重命名全部稳定 ID（link/joint/actuator/collider/
  sensor + parent_link_id/joint_id/link_id 引用字段）。多机必须克隆而非共享：
  MuJoCo 按名称解析 ID、四旋翼推进层独占 rotor 资源、attachment 按 ID 寻址。

swarm controller: IrisSwarmDeliveryController
  每机一个 ObstacleDeliveryPilot（beefoundrysim.controllers.iris_obstacle_navigation）
    ├─ 任务 FSM：spool→takeoff→pickup→capture→lift→navigate_loaded*→dropoff→retreat
    ├─ 12 路测距 → LiveOccupancyGrid（含先验障碍膨胀 + 2 s TTL 动态观测）
    ├─ IncrementalAStarPlanner 分帧重规划（route 失效 / 1.5 s 停滞触发）
    ├─ 反应式避障：排斥场 + 顺时针沿墙 + 机间排斥（intruders ≤1.8 m）
    └─ 机间去冲突：邻机作为 TTL 瞬时障碍注入占用栅格
  聚合 NavigationUpdate（最差状态 + 各机摘要）供前端 Navigation 面板展示
```

## 关键工程决策

- **公园视觉用 Optimized 流式配置，不用 Full**：Full 配置 9500 万顶点（95 块
  ≈ 3.3 GB GPU 缓冲）会把普通显卡拖入假死，浏览器表现为“场景永远加载不出来”；
  Optimized 1150 万顶点（50 块）在实测中 10 秒内全部流式完成，且保留全部
  结构、树木、道路与硬地景观，仅省略密集绘制植被。加载管线本身毫秒级/块，
  卡顿全部来自渲染负载。
- **公园不能作为单 mesh 碰撞体**：MuJoCo 对 mesh geom 按凸包碰撞，整园 192 盒
  OBJ 的凸包会在公园上空形成隐形壳面（实测任务点上空 0.2–1.0 m）。因此物理侧
  使用隐形地板 + 显式构筑物/售货亭 primitive 盒；`stream_scene_id` 使前端只渲染
  流式公园而忽略 primitive。
- **地形感知的任务点**：pad/载荷/抓取下降高度按碰撞代理实测地形高度放置
  （`TERRAIN_HEIGHTS`），pickup 与 dropoff 地形不同高时控制器使用独立的
  `dropoff_hook_height`。
- **防自反射两层过滤**：机腹悬挂载荷（机心下 ~0.3 m）摆动 + 机体倾转会被自身
  测距射线扫到，产生"幽灵障碍"毒化路线检查与局部避障。对策：(1) 射线安装高度
  抬至机心 +0.22 m；(2) `minimum_hit_distance`（蜂群用 0.55 m）同时应用于占用
  栅格与反应式避障层。
- **动态障碍停靠位在走廊外**：未激活时停泊在工作区边缘，仅激活窗口内横穿走廊，
  避免常驻车体永久堵死规划路线。
- **走廊宽度 ≥ ~2 m**：先验障碍布局保证 A* 规划出的路径不贴壁，否则反应式排斥
  会在窄缝中与轨迹跟踪互相抵消导致停滞。

## 验收

`tests/test_drone_park_delivery.py` 自动验证：克隆 ID 全局唯一且场景校验/物理
预检通过；每条任务航线绕开先验障碍（直线必被阻挡、规划路线必畅通）；完整仿真中
三个配送任务全部 `completed` 且载荷落点在 dropoff 容差内；资源缺失时控制器
reset 显式报错。

## 边界

- 机间避让为 2D 同高度层（巡航统一 1.6 m），无垂直分层交通管理。
- 公园仅任务走廊（x∈[-108,-86], y∈[-14,13]）具备实体碰撞；其余区域为流式视觉。
- `ControllerAction.navigation` 单值，蜂群只上报聚合导航状态。
