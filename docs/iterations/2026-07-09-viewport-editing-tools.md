# Viewport Editing Tools

日期：2026-07-09

## 目标

推进 Iteration B，补齐 primitive viewport 的基础编辑工具，让用户可以更自然地选择、观察和变换 actor。

## 主要改动

- 新增 viewport 内工具条：
  - translate。
  - rotate。
  - scale。
  - frame selected。
  - isometric/front/right/top camera view。
- 新增快捷键：
  - `W` translate。
  - `E` rotate。
  - `R` scale。
  - `F` frame selected。
  - `1` front view。
  - `3` right view。
  - `7` top view。
  - `0` isometric view。
- 扩展 transform 回写：
  - translate 回写 position。
  - rotate 回写 rotation。
  - scale 回写 scale。
- 新增 selection outline。
- Frame selected 会聚焦当前选中 actor；未选中时聚焦全部 actors。
- Simulation playback 时保留 selection outline，但自动 detach transform gizmo，避免 runtime pose 和 authoring edit 混在一起。
- Qt WebChannel 增加普通浏览器 guard，方便后续 viewport browser smoke test。
- 更新 README 和产品计划。

## 验证

- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m pytest`：`11 passed`。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m ruff check .`：通过。
- `git diff --check`：通过。

## 已知限制

- 尚未实现 snap to grid。
- 还没有 Playwright/QtWebEngine 视觉 smoke test。
- Selection outline 当前是 bounding box helper，不是后处理描边。
- Camera shortcuts 是基础固定视角，尚未加入平滑过渡。

## 下一步

- 增加 snap to grid。
- 增加 viewport browser smoke test 和 canvas nonblank check。
- 增强 toolbar 状态和 simulation/editing 状态反馈。
