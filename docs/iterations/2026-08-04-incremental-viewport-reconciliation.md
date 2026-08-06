# Incremental Viewport Scene Reconciliation

日期：2026-08-04  
提交：待提交

## 目标

消除场景编辑中的全量 Three.js 重建：添加或删除一个资产时，已有资产不得重新创建、重新下载几何或重新上传 GPU 资源。

## 主要改动

- 使用稳定 actor ID 对作者态场景和 Three.js 渲染对象做增量对账。
- 为每个 actor 保存渲染签名；只在该 actor 的类型、资产、属性或机器人 articulation 改变时定向重建。
- 新增 actor 只创建自己的 `Object3D`，删除 actor 只释放自己的 geometry、material 和 texture。
- 将全局场景加载版本替换为 per-actor revision，防止无关场景编辑取消或重启已有 OpenUSD 异步加载。
- 保留未变 actor 的对象身份、选中状态、变换控制器以及已经驻留的 GPU 资源。
- 保留 transform-only 快速路径，不因移动、旋转或缩放重新请求几何。
- 大型地图保持自动取景计算出的相机相关雾效距离；同一环境内新增资产不再把雾效重置为 `18–60m`，避免地图短暂变白。

## 验证

- TypeScript 类型检查和生产构建通过。
- 前端 store、simulation、trajectory、kinematics、geometry bundle 和 Vite 配置测试通过。
- Python：254 passed，3 skipped；Ruff 与 mypy 通过。
- Playwright：16 个完整浏览器工作流全部通过。
- 浏览器回归验证：Vehicle Hanger 加载后再添加 Box，`/geometry/` 请求总数保持为 1。
- 浏览器回归验证：移动缓存 OpenUSD actor 不重新加载几何，编辑属性后仍保持选中。
- 浏览器回归验证：后海地图添加 Box 前后的 fog near/far 和着色保持一致，地图几何请求保持为 1。

## 已知限制

- 修改单个 actor 的任意 `properties` 字段目前会重建该 actor；后续可继续把材质、碰撞调试和纯物理字段拆成更细的局部更新。
- 首次加载的新资产仍需正常解析、下载并创建 GPU 资源；本轮优化针对已有资产的重复工作。

## 下一步

- 在大型多资产场景中增加帧时间、GPU 内存和几何请求计数的性能基线。
- 视实际编辑热点，将单 actor 重建进一步细分为材质更新、碰撞可视化更新和机器人拓扑更新。
