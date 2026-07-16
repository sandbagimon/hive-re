# Qt Robot UI E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine、QWebChannel 和 TypeScript 页面中验证外部 USD 机械臂 UI，而不依赖原生文件对话框。

## 主要改动

- MainWindow 支持注入 project root，测试将 OpenUSD cache 和 metadata 隔离到临时目录。
- Window 暴露受控 `simlabEditor` automation API：path import、state JSON、有效 joint selection。
- Automation API 复用正式 `importOpenUsdPath` 和 EditorStore，不增加旁路 scene mutation。
- 页面发布明确 ready flag，自动化会等待 QWebChannel、assets 和初始 Store 同步完成。
- 新增 opt-in QtWebEngine E2E，默认普通测试环境跳过，显式环境变量启用。
- E2E 验证 2 个 joint、唯一 selected row、Joint Inspector、2 个 Jog 按钮和有效 canvas 尺寸。
- 截图采样验证页面非空，并人工检查 WebGL grid、robot visual、child Link outline 和面板排版。
- Joint range 使用 3 位小数，避免双精度文本在紧凑 Inspector 中裁切。

## 验证

- 默认门禁：82 passed，2 skipped。
- `SIMLAB_QT_WEBENGINE_E2E=1 ... pytest tests/test_qt_robot_ui.py`：1 passed。
- QtWebEngine 在无 Vulkan 环境自动 fallback 到 software rendering，WebGL viewport 非空。
- 验收截图：`/tmp/simlab-robot-joint-ui.png`。

## 下一步

在同一真实页面中点击 Run/Jog/Pause/Reset，验证 live qpos、Link pose 和 Home 恢复。
