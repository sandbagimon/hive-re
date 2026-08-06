# Viewport 快捷键文档与前端入口

日期：2026-08-03

## 目标

把 Viewport 鼠标操作、快捷键和大型场景导航方法整理成正式文档，并允许用户从浏览器前端直接进入。

## 主要改动

- 新增随前端独立发布的中文静态指南 `frontend/public/docs/viewport-controls.html`。
- 在顶部命令栏新增 **Shortcuts** 入口，以新标签页打开指南，避免打断当前编辑会话。
- 新增仓库文档 `docs/VIEWPORT_CONTROLS.md`，记录快捷键约定和发布路径。
- 增加静态资源与浏览器入口测试。

## 验证

- 前端生产构建必须包含 `dist/docs/viewport-controls.html`。
- Playwright 从命令栏打开文档并检查核心快捷键内容。
- Python 静态测试检查文档和入口声明。

## 已知限制

- 文档当前为静态内容；新增或修改快捷键时需同步更新 HTML 与 Markdown。

## 下一步

- 若快捷键数量继续增长，可把快捷键声明抽成共享数据并在编辑器和文档页面中共同渲染。
