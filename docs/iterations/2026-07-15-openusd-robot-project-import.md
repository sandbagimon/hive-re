# OpenUSD Robot Project Import

日期：2026-07-15
提交：待提交

## 目标

把 articulation mapper 接入用户实际使用的 Import USD、项目缓存、Bridge RPC 和 Editor Store，使外部
机器人资产进入可保存、可移动、可 undo/redo 的 authoring scene。

## 主要改动

- 正式 Import USD 自动识别 `PhysicsArticulationRootAPI`；机器人不再错误进入合并 Mesh object 路径。
- 新增 robot asset cache，写入源 USD、`robotics.json`、`manifest.json` 和 `import-report.json`，
  metadata 最后注册，blocking dependency 不留下半成品资产条目。
- 成功导入后将 source URI 重写为项目相对路径；Scene 保存后移动整个项目目录仍可加载模型与源 USD。
- stage dependency report 纳入 referenced layers；源目录内依赖按相对结构复制，源目录外依赖明确阻止。
- Bridge Import USD payload 增加 RoboticsModel。
- TypeScript Scene 类型增加 robotics contract；EditorStore 在添加 robot actor 时合并 articulation，保持
  dirty/undo/redo 的单次提交语义。
- 同步更新 checked-in generated JavaScript 和前端 Store 测试用例。

## 验证

- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：60 passed，1 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- `git diff --check`：通过。
- 当前环境没有 `node` 和 `npm`，无法运行 TypeScript typecheck/frontend test；本轮 TS 与 generated JS
  已同步人工核对，仍需在具备 Node.js 的环境补跑。

## 已知限制

- Scene Tree 当前仍只显示 robot actor，不展开 Link/Joint。
- viewport 尚未消费 RoboticsModel visual geometry，因此导入后机器人结构尚不可见。
- MJCF exporter 和 MuJoCo runtime 尚不支持 articulation。
- 源目录外部的依赖暂时阻止导入，不自动重写 composition arc。

## 下一步

在 TypeScript Scene Tree 和 three.js viewport 中展示 Robot/Link/Joint 层级并渲染逐 Link primitive
VisualGeometry；保持 authoring transform 与后续 simulation transform 分离。
