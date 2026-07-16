# Sensor Inspector

日期：2026-07-16
提交：待提交

## 目标

在 TypeScript 编辑器中展示机器人传感器，并检查 MuJoCo fixed-step runtime 发布的实时 joint-state sample。

## 主要改动

- EditorStore 增加独立 sensor selection，并与 actor/joint selection 互斥。
- Robot Tree 在 articulation links/joints 后展示 sensors；选择行为不修改 scene、dirty 或 undo/redo。
- Sensor Inspector 展示 stable ID 对应的 name、type、joint、rate、sequence、simulation time、qpos 和 qvel。
- Runtime Inspector 仅消费 SimulationState latest samples，UI render 不参与传感器采样。
- 选择 joint-state sensor 时，viewport 高亮其关联 joint 的 child link。
- Automation API 增加 `selectSensor`，用于真实 QtWebEngine 工作流验收。

## 验证

- EditorStore 测试覆盖合法/非法 sensor selection、joint/sensor 互斥和非 dirty 行为。
- 静态 web asset 测试覆盖 sensor tree、Inspector 与 runtime field wiring。
- 真实 QtWebEngine 从外部 OpenUSD 双关节手臂打开项目，选择 50Hz sensor，启动 MuJoCo 后暂停并逐字段比对 Store/DOM sample。
- Qt 验收保存 viewport 截图并检查画面非空和颜色分布。
- 完整 Python、Ruff、Mypy、TypeScript build 和 frontend tests 通过。

## 已知限制

- Inspector 只显示每个 sensor 的 latest sample，不保留历史曲线。
- Recording JSON/CSV 尚未包含 sensor emitted samples。
- 第一版仅支持 articulation joint_state sensor。

## 下一步

让 Recording 选择并导出按 fixed physics step 实际发出的 sensor samples，避免重复 latest 值。
