# 无人机物理取送示例

BeeFoundrySim 提供了一条可直接运行的 Iris 四旋翼 A→B 取送闭环。这里的起飞、姿态变化、货物增重、
接触、携带和释放都由 MuJoCo 计算；three.js 只显示后端返回的刚体状态，不伪造货物轨迹。

## 运行

在仓库根目录启动允许执行可信 Python Controller 的后端：

```bash
./start_backend.sh --allow-controller-execution
```

另开一个终端启动前端：

```bash
./start_frontend.sh
```

打开 `http://127.0.0.1:5173` 后：

1. 点击 **Open**，选择 [`examples/drone_delivery/scene.json`](../examples/drone_delivery/scene.json)。
2. 在 Scene Tree 中选择 **Pegasus Iris Quadcopter**。
3. 在 Controller 面板点击 **Load**，选择
   [`examples/controllers/iris_payload_delivery.py`](../examples/controllers/iris_payload_delivery.py)。
4. 确认这是可信的本地脚本，点击 **Run**；可选择 `2x` 加速观察。

预期过程为预转、起飞、飞往 Pickup A、下降并接触货物、锁定、负载起飞、飞往 Dropoff B、
下降释放、退离和悬停。HUD 最终显示 `task completed`，货物静止在 B 点附近。

## 场景契约

`Scene.attachments` 声明可动态启停的物理连接。每个连接使用稳定的 body ID 和两个局部锚点，
并定义抓取距离、相对速度、持续时间和是否要求真实接触。MuJoCo 适配器支持保持自由转动的
site-to-site `connect` 和同时锁定位置/姿态的 `weld`。

配送示例使用四吸盘真空抓手：一个承力板、安装杆和四个独立 cylinder 接触几何固定在 Iris
机体下方。真空请求在最后下降阶段预启，但只有吸盘与外卖袋碰撞体形成连续接触、锚点距离不超过
`0.035 m`、相对速度不超过 `0.14 m/s` 并持续 `0.25 s` 后，运行时才激活刚性 `weld`。

`Scene.delivery_tasks` 独立声明任务成功条件，包括 payload body、A/B 位置、落点容差、静止速度
和稳定时间。它不控制无人机，只根据真实运行状态依次报告 `waiting_pickup`、`in_transit`、`released`、
`settling` 或 `completed`。

Controller 通过稳定 ID 读写连接，不接触 MuJoCo 对象：

```python
attachment = observation.attachments["attachment_iris_payload_hook"]
return ControllerAction(
    actuator_controls=rotor_speeds,
    attachment_commands={"attachment_iris_payload_hook": should_hold},
)
```

只有同时满足请求、距离、相对速度、持续时间和可选接触条件时，运行时才会激活连接。释放请求
立即关闭连接。Reset 会恢复 `initially_active`，不存在瞬移式“吸附”。

## REST 控制

人工或外部编排器可通过同一稳定 ID 控制连接：

```http
PUT /api/v1/simulations/{simulation_id}/attachments
Content-Type: application/json

{
  "commands": {
    "attachment_iris_payload_hook": true
  }
}
```

响应和 WebSocket simulation state 都包含 `attachments` 与 `delivery_tasks`。连接命令会整体校验；
未知 ID 或非布尔值不会部分应用。

## 当前物理边界

示例使用真实刚体质量、惯量、碰撞、重力、四旋翼二次推力/反扭矩、位置与姿态闭环、负载质量
前馈以及 MuJoCo wind。旋翼转动的画面是由真实 actuator 转速驱动的降速可视化，但旋翼网格本身
不负责产生推力。

货物按 36×28×22 cm、0.35 kg 的保温外卖袋建模。碰撞继续使用稳定箱体几何；three.js 外观使用
圆角软包主体、独立上盖、双拉链、包边、加强缝、双提手、反光条、拉链头和防滑脚。袋体采用
1254×1254 炭黑色 600D Oxford 编织布高清基础色贴图，并叠加 woven-fabric bump、roughness、
sheen 和 PMREM 环境反射。视觉细节不制造额外 MuJoCo 薄片碰撞，避免提手、拉链和包边导致
接触抖动或改变原有抓取标定。

当前真空吸附由接触门控后的刚性约束表达，尚未计算真空压力、泄漏率、吸盘变形、最大剥离力或
连接破坏；气动也尚未包含桨叶入流、地效、电池压降和电机一阶响应。改变 Iris 几何、质量、
转子布局或货物质量后，需要重新标定 mixer 和控制增益。
