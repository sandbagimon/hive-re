# Physics Validation Preflight

日期：2026-07-10

## 目标

在 Run、Step 和 Export MJCF 前发现无效物理配置，并在 UI 中给出可定位的问题，而不是让导出器或 MuJoCo 以模糊异常失败。

## 主要改动

- 新增统一的 physics preflight report model。
- 校验 object actor 的 primitive、dynamic/static、mass 和 friction。
- 拒绝 dynamic plane、重复 actor id 和不支持的 primitive。
- 属性校验通过后生成 MJCF，并调用 MuJoCo compiler 做实际 load check。
- Export、Run、Step 共用同一套 preflight。
- 阻塞错误在对话框中显示摘要和完整 details，并同步写入 Console Panel。
- 静态 actor 的 mass 作为非阻塞 warning 提示。
- 新增 preflight 成功、字段错误、warning 和 MuJoCo compile failure 测试。

## 验证

- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m pytest`：`20 passed`。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m ruff check .`：通过。
- `/home/ubuntu/miniforge3/bin/conda run -n hive python -m compileall -q src tests`：通过。

## 后续

- 将 validation report 扩展成可常驻的 Validation Panel。
- 支持点击 issue 选择对应 actor。
- 为常见问题增加 quick fix。
