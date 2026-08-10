# Insulated Takeout Bag

日期：2026-08-10
分支：`feature/drone-obstacle-avoidance`

## 目标

将无人机配送任务中的瓦楞纸箱替换为高清、真实且适合近景观察的保温外卖袋，同时保持现有质量、
碰撞、真空抓取标定、避障路线和任务成功条件不变。

## 实现

- Scene actor 保持 `actor_003`、36×28×22 cm 箱体碰撞、0.35 kg 质量、A/B 位置和 attachment
  child anchor；名称改为 `Insulated Takeout Bag`，视觉样式改为 `insulated_delivery_bag`。
- three.js 将 primitive box 外观替换为 bevelled rounded extrusion，并增加独立上盖、双拉链轨道、
  橙色包边、四条加强缝、双提手、前部反光条、拉链头和四个防滑脚。
- 使用内置 image generation 生成 1254×1254、无品牌/文字的炭黑色 600D Oxford 编织布基础色，
  保存为 `frontend/public/textures/delivery-bag-oxford-albedo.png`。
- `woven_fabric` 程序表面提供与光照交互的 bump、roughness 和 sheen；高清图只负责真实纤维颜色，
  避免把光影烘焙进纹理后与场景照明冲突。
- 纹理异步加载具有 actor revision 栅栏；actor 被替换时会丢弃迟到结果。材质/纹理释放改为对象级
  去重，允许袋体和上盖安全共享同一高清贴图。

## 物理边界

- 提手、拉链、包边、反光条和防滑脚只属于 viewport visual，不导出为 MJCF geom。
- 碰撞和惯量仍来自稳定箱体，因此不引入细小几何接触抖动，也不需要重新标定飞控。
- `physics.material` 从 wood 改为 rubber 以匹配袋体语义；显式 friction、质量和 contact 参数不变。

## 验证

- TypeScript、前端模块测试和 Vite production build。
- 浏览器断言高清贴图加载完成，分别截图完整任务场景和外卖袋近景。
- MuJoCo 原配送和实时避障配送回归，确认抓取、负载飞行、重规划和 B 点释放结果保持完成。
