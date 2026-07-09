# Scene Editing Reliability

日期：2026-07-09

## 目标

推进 M2 / Iteration C 的第一部分，让基础 scene edit 不容易丢改动，并且常规操作可以撤销和重做。

## 主要改动

- 新增 `SceneHistory`：
  - 使用 scene snapshot 管理 undo stack。
  - 使用 redo stack 支持重做。
  - 通过 saved snapshot 判断 dirty state。
  - 支持 `mark_saved()` 和 `reset()`。
- 主窗口新增 dirty state：
  - 未保存改动时窗口标题显示 `*`。
  - Save 成功后清除 dirty。
  - New/Open/Close 前提示 Save / Discard / Cancel。
- 主窗口新增 undo/redo：
  - Toolbar 增加 Undo / Redo。
  - 支持 `Ctrl+Z` 和 `Ctrl+Shift+Z`。
  - 覆盖 add actor、delete actor、rename actor、property transform edit、viewport transform edit。
- Scene edit、undo、redo、new/open 会清理当前 runtime simulation state，避免继续使用旧 MuJoCo model。
- Viewport gizmo 的 transform 回写仍然在 mouse up 后发生，因此一次拖动只进入历史栈一次。
- 新增 `SceneHistory` 单元测试。
- 更新 README 和产品计划。

## 验证

- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m pytest`：`13 passed`。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m ruff check .`：通过。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m compileall -q src tests`：通过。

## 已知限制

- Undo/redo 当前基于完整 scene snapshot，适合 MVP；超大 scene 后续可能需要 command-based history。
- Duplicate actor、context menu 和 auto-save recovery 尚未实现。
- Property Panel 的 spinbox 连续编辑会按每次 value change 入栈，后续可合并为编辑事务。

## 下一步

- 增加 duplicate actor。
- 增加 Scene Tree context menu。
- 增加 auto-save recovery file。
- 为 transform/property 编辑加入更细的 history transaction 合并。
