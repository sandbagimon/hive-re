# Requirements Smoke Fix

日期：2026-07-09
提交：本次 requirements 修复提交

## 目标

修复 clone/pull 后直接使用 `requirements.txt` 安装不够稳、不够直观的问题。此前 `requirements.txt` 主要依赖 `-e .` 从 `pyproject.toml` 间接拉取运行依赖，对新环境使用者不够清楚。

## 主要改动

- 将 `requirements.txt` 改为显式列出依赖：
  - `pip`
  - `setuptools`
  - `wheel`
  - `PySide6`
  - `mujoco`
  - `pytest`
  - `ruff`
  - `mypy`
- 保留 `-e .`，用于从当前 checkout 安装 SimLab 包本身。
- README 安装步骤增加：
  - 必须在 repository root 执行。
  - 先升级 `pip setuptools wheel`。

## 验证

- 创建临时干净 venv。
- 只执行 `python -m pip install -r requirements.txt`。
- 验证以下 import 成功：
  - `PySide6.QtWebEngineWidgets.QWebEngineView`
  - `mujoco`
  - `simlab`

## 已知限制

- `requirements.txt` 仍未 pin 精确版本。
- 安装时可能出现 pip 查询新版本的 SSL warning，但本次 smoke test 中不影响依赖安装和 import 验证。

## 下一步

- 后续可增加 `constraints.txt` 或 lock file，进一步提升跨机器复现性。
