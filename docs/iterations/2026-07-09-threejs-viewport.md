# Three.js Viewport

日期：2026-07-09
提交：`28f2d8f feat: add local three.js viewport`

## 目标

按照“不侵权复刻能力结构”的路线，将 SimLab 中间区域从 placeholder 替换成真正可交互的本地 3D viewport。物理继续使用 MuJoCo，3D 渲染和编辑控制使用 MIT 许可证的 three.js。

## 主要改动

- 新增 `src/simlab/web_viewport/` 本地 web viewport 资源目录。
- vendored three.js r160 文件：
  - `three.module.js`
  - `OrbitControls.js`
  - `TransformControls.js`
  - `THREE_LICENSE.txt`
- 将 three.js examples controls 的 import 改为本地相对导入，避免依赖 CDN 或 npm。
- 新增 `index.html`、`style.css`、`viewport.js`。
- 新增 `WebViewport` Qt 组件：
  - 使用 `QWebEngineView` 承载本地 three.js viewport。
  - 使用 `QWebChannel` 建立 Python 和 JavaScript 双向通信。
- 主窗口从 `ViewportPlaceholder` 切换到 `WebViewport`。
- viewport 当前支持：
  - 渲染 box、sphere、cylinder primitive actors。
  - orbit camera。
  - grid 和 axes。
  - 点击 3D 物体选择 actor。
  - 选择状态同步到 Python 主窗口、Scene Tree 和 Property Panel。
  - 选中 actor 后显示 translate gizmo。
  - 拖动结束后将 position 回写到 Python scene model。
- 更新 `pyproject.toml` package data，确保 HTML/CSS/JS/vendor 文件随包分发。
- 更新 README：
  - viewport 不再是 placeholder。
  - 记录 three.js vendored 位置和 MIT license。
- 新增 viewport assets 测试。

## 验证

- `.\.venv\Scripts\python.exe -m pytest`：`9 passed`。
- `.\.venv\Scripts\python.exe -m ruff check .`：通过。
- `.\.venv\Scripts\python.exe -m compileall -q src tests`：通过。
- QtWebEngine offscreen 主窗口构造检查：通过。

## 已知限制

- viewport 现在渲染的是 SimLab scene model，不是 MuJoCo 原生 renderer。
- transform gizmo 当前只实现 translate。
- rotation 和 scale gizmo 尚未接入。
- MuJoCo 仿真状态还没有实时同步回 three.js viewport。
- 只支持 primitive object actor，不支持 robot、terrain、camera、light 的完整可视化。

## 下一步

- 做 MuJoCo state sync：
  - 运行仿真时从 MuJoCo body pose 读取位置和姿态。
  - 将 pose 通过 Python/Qt bridge 推送给 three.js viewport。
  - viewport 实时更新 actor mesh transform。
- 增加 rotate/scale gizmo。
- 增加 selection outline、坐标轴切换和视角快捷按钮。
