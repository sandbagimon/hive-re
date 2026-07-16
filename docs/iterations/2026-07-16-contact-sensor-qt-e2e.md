# Contact Sensor Qt E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine 编辑器中验收外部 USD 机械臂 contact sensor 的选择、运行时更新、viewport link 高亮和 Reset。

## 主要改动

- 添加独立 QtWebEngine contact sensor E2E，不改变既有 joint/IMU recording 场景。
- 测试项目包含外部 USD 两关节机械臂、forearm collider-scoped sensor 与 scene 中可见静态平台。
- 从 Scene Tree 选择 sensor，验证 collider scope 名称和对应 SecondSegment viewport HUD/highlight。
- 从 Joint Inspector 设置 shoulder 目标并运行 MuJoCo，随后回到 Sensor Inspector 验证全部 contact 字段。
- 验证 contact sensor 不出现在当前只支持 joint-state/IMU 的 Recording Panel。
- Pause 后保存离屏视觉截图，Reset 后验证 runtime 与 Inspector count 清零。

## 验证

- 真实 QWebEngine + MuJoCo + OpenUSD E2E：1 passed。
- 接触时 simulation time 约 0.38s，contact count 为 2，normal force/impulse 与 UI 格式化值一致。
- Tangent force、首个 world point 和首个 world normal 与 SimulationState 逐项一致。
- `/tmp/simlab-contact-sensor-ui.png` 视觉检查通过：viewport 非空、机械臂/平台可见、link 高亮清晰、Inspector 无重叠。

## 已知限制

- Contact sensor 仍未进入 recording/export contract。
- E2E 使用 offscreen Qt 平台；不同桌面缩放比例仍需后续 CI 矩阵覆盖。

## 下一步

建立 contact typed recording contract 与 stable JSON/CSV columns。
