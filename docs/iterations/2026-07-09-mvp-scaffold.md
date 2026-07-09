# MVP Scaffold

日期：2026-07-09
提交：`5340052 chore: scaffold simulation-first desktop MVP`

## 目标

创建 SimLab 的初始可运行项目骨架。该版本聚焦 simulation-first MVP，不引入云服务、登录、在线资产市场，也不使用 OrcaLab 的品牌、资产、业务逻辑或专有运行时。

## 主要改动

- 建立 Python `src/` 项目结构和现代 `pyproject.toml`。
- 添加 PySide6 桌面应用入口：`python -m simlab.app`。
- 添加主窗口布局：
  - 顶部工具栏：New Scene、Open、Save、Save As、Export MJCF、Run Simulation、Stop Simulation。
  - 左侧 Asset Browser。
  - 左下 Scene Tree。
  - 中间 Viewport Placeholder。
  - 右侧 Property Panel。
  - 底部 Console Panel。
- 添加核心 scene model：
  - `Transform`
  - `Actor`
  - `Scene`
- 添加 `scene.json` 序列化和反序列化能力。
- 添加 `ProjectService`：
  - 保存 scene JSON。
  - 加载 scene JSON。
  - 最小验证 scene version、actor id 唯一性、transform 向量长度。
- 添加 `SceneService`：
  - 新建场景。
  - 添加、删除、重命名 actor。
  - 更新 transform 和 properties。
  - 生成稳定 actor id，例如 `actor_001`。
- 添加 primitive 资产：
  - Box
  - Sphere
  - Cylinder
- 添加 MJCF exporter：
  - 将 box/sphere/cylinder 转成 MuJoCo geom。
  - 导出到 `exports/scene.xml`。
- 添加 headless MuJoCo runner：
  - 加载 MJCF。
  - 创建 `MjModel` 和 `MjData`。
  - 运行短仿真循环并输出 step 日志。
- 添加 `SimLabEnv` gym 风格 stub。
- 添加 demo scene 和 pytest 测试。
- 添加 README、LICENSE、`.gitignore`。

## 验证

- `python -m pytest`：初次验证为 `7 passed, 1 skipped`，因为当时 MuJoCo 尚未安装。
- 安装完整依赖后：`8 passed`。
- `python -m ruff check .`：通过。
- `python -m compileall -q src tests`：通过。
- PySide6 offscreen 主窗口构造检查：通过。

## 已知限制

- 中间 viewport 只是 placeholder，没有真实 3D 渲染。
- MuJoCo runner 是 headless，不提供 GUI viewer。
- MJCF export 只支持 primitive object actor。
- rotation 导出尚未完整实现。
- gym environment 只是未来扩展 stub。

## 下一步

- 将 placeholder viewport 替换为真正的 3D viewport。
- 建立不侵权的开源渲染路径。
- 后续将 MuJoCo state 同步回 viewport。
