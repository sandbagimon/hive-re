# Joint Control UI

日期：2026-07-15
提交：待提交

## 目标

让用户从 robot Property Panel 直接操作外部 USD 机械臂的 position joints，并查看 MuJoCo 实时状态。

## 主要改动

- robot Inspector 按 position actuator 生成 joint slider 和数值输入，范围来自 control_range。
- 显示每个 joint 的实时 qpos/qvel，目标值来自 actuator ctrl，未加载 runtime 时使用 initial position。
- Home 按 stable joint ID 恢复所有 position joint 初始目标。
- 控制通过 `setJointTargets` RPC 进入 MuJoCo，不修改 Scene.robotics，不产生 dirty/history 记录。
- 命令成功后 editor 进入 paused simulation state，viewport 立即使用 runtime Link pose。
- 安装并启用 hive 环境现有 Node.js，使用 `tsc` 正式生成 checked-in JavaScript。
- 增加 QWebChannel RPC 测试，证明 UI 使用的 bridge 方法可创建 Session 并更新 actuator ctrl。

## 验证

- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：65 passed，1 skipped。
- ruff、mypy、`npm run typecheck`、`npm run build`、`npm run test:frontend` 全部通过。
- QtWebEngine offscreen smoke：`loadFinished=True`，three.js viewport 软件渲染截图成功。
- 自动点击 Import USD 的 robot 专用截图被原生 QFileDialog 模态窗口阻塞，已终止；需在交互式显示
  环境复核完整 robot tree/slider 画面。

## 已知限制

- slider 当前在 change 时发送目标，不做连续 input 节流。
- 还没有 command timeout、controller fault 状态和持续运行 soak test。
- Link/Joint inspector 仍不是独立 selection model。

## 下一步

执行 Gate 1 外部机械臂端到端验收，补充控制安全、短时 soak 和保存重开后的行为一致性测试。
