# Venv Requirements

日期：2026-07-09
提交：`5b83ab6 chore: add venv requirements setup`

## 目标

将项目运行环境从全局 Miniforge Python 切换为项目内 `.venv`，并提供 `requirements.txt`，让安装和运行路径更清晰、可复现。

## 主要改动

- 新增 `requirements.txt`。
- `requirements.txt` 使用 `-e .` 安装当前项目本身。
- 将开发工具加入 requirements：
  - `pytest`
  - `ruff`
  - `mypy`
- 更新 README 安装说明：
  - `python -m venv .venv`
  - `.\.venv\Scripts\activate`
  - `python -m pip install -r requirements.txt`
- 将测试命令统一成：
  - `python -m pytest`
- 创建并验证本地 `.venv`：
  - 环境路径：`D:\orca-re\.venv`
  - Python 路径：`D:\orca-re\.venv\Scripts\python.exe`
- 确认 `.venv` 被 `.gitignore` 排除，没有进入 Git。

## 验证

- `.\.venv\Scripts\python.exe -m pytest`：`8 passed`。
- `.\.venv\Scripts\python.exe -m ruff check .`：通过。
- 确认 `simlab` 从 `D:\orca-re\src\simlab\__init__.py` 加载。

## 已知限制

- `requirements.txt` 目前未 pin 精确版本，只约束最小版本。
- 本地 `.venv` 不提交到仓库，需要每台机器自行创建。

## 下一步

- 如需更强可复现性，可后续增加 lock file 或 constraints 文件。
- 如需发布桌面应用，可后续增加打包流程。
