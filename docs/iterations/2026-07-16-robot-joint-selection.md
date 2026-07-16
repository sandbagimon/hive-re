# Robot Joint Selection

日期：2026-07-16
提交：待提交

## 目标

让外部机械臂的关节层级可导航，并将 Scene Tree、Inspector 和 3D viewport 聚焦到同一个 joint。

## 主要改动

- EditorState 增加 transient `selectedJointId`，不写 Scene JSON、不触发 dirty/undo。
- Store 只接受确实属于指定 robot actor articulation 的 joint ID。
- 选择 actor、删除 actor 和新建/打开 Scene 会清理 joint selection；history restore 保留仍有效的选择。
- Scene Tree joint 从静态行变为可选择按钮，并提供独立 selected 状态。
- 选 joint 后 Inspector 显示 type、parent/child Link、axis、range 和实时 position。
- Joint Control 聚焦当前 joint，Home 只恢复该 joint；选择 actor 时仍显示全部 joint。
- viewport 增加 `selectedLinkId`，用独立颜色、emissive 和 BoxHelper 高亮 joint child Link。
- Frame Selected 和 camera shortcuts 使用 child Link bounds；runtime Link pose 更新后 outline 同步移动。

## 验证

- TypeScript typecheck、正式 build 和 frontend Store tests 通过。
- Store test 覆盖有效 joint selection、无效 ID 拒绝、actor selection 清理。
- 静态 UI contract 覆盖 Scene Tree selection、viewport Link selection 和 runtime Inspector。
- 完整 Python、ruff、mypy 门禁见提交记录。

## 下一步

建立受控 Editor Automation API，并用真实 QtWebEngine 页面完成 robot UI 截图验收。
