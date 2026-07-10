平台差距

| 能力 | SimLab 当前 | OrcaLab 公开能力 | Isaac Sim / Isaac Lab |
|---|---|---|---|
| 场景表示 | scene.json + MJCF | 宣称支持 OpenUSD、SimReady 资产 | OpenUSD 原生 |
| 机器人模型 | 无 articulation | 宣称支持多形态机器人 | URDF/MJCF/CAD、articulation |
| 物理 | MuJoCo primitive 刚体 | 宣称高精度、多物理场 | PhysX/Newton、车辆、关节、SDF |
| 渲染 | three.js 标准渲染 | 宣称高保真实时渲染 | RTX、物理传感器、照片级渲染 |
| 传感器 | 无 | 宣称 RGB/Depth/IMU/Lidar | Camera/Lidar/IMU/Contact 等完整体系 |
| 数据生成 | 无 | 宣称全维度合成数据 | Replicator、标注器、COCO/KITTI |
| 控制器 | 无 | 宣称开放接口和训练闭环 | Python、OmniGraph、ROS 2 |
| 训练环境 | stub | 宣称多环境、多机器人并发 | Isaac Lab GPU 并行、多 GPU/节点 |
| 资产库 | 6 个 primitive | SimReady 和行业场景资产 | USD/CAD/机器人生态 |
| 扩展接口 | JSON RPC | 宣称 MCP、CLI、30+ 接口 | Python、Kit extensions、ROS 2 |
| 部署重点 | 本地轻量、MuJoCo | 轻量开发版 + 企业训练平台 | NVIDIA GPU 高保真和大规模训练 |

