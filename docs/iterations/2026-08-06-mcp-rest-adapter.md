# MCP REST Adapter

日期：2026-08-06

## 目标

在不破坏前端、API、应用服务和仿真后端边界的前提下，让 MCP 客户端能够检查项目、运行
preflight，并控制一个完整的仿真生命周期。

## 主要改动

- 新增独立 `simlab-mcp` 进程，只通过 `/api/v1` 调用现有 REST 资源，不直接导入
  `ResourceManager`、MuJoCo 或服务器资产目录。
- 基于官方 MCP Python SDK v2 提供 stdio 与 Streamable HTTP 两种传输。
- 提供 17 个 structured-output tools，覆盖项目、资产、preflight、MJCF 导出、仿真生命周期、
  关节目标和执行器控制。
- 提供 1 个固定 resource、3 个 URI template resources 和 1 个只读项目审查 prompt。
- 沿用 `SIMLAB_API_TOKEN` Bearer 认证；Streamable HTTP 默认只监听 loopback，非本地暴露要求
  显式 `--allow-remote` 并提示部署认证/TLS 代理。
- 新增 `start_mcp.sh`、`mcp` optional dependency、`simlab-mcp` console entry point 和独立接入文档。

## 验证

- `python -m pytest -q tests/test_mcp_adapter.py`：4 passed。
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：沙箱内 268 passed、3 skipped；仅 2 个
  gRPC 监听随机端口的测试被沙箱阻止，沙箱外补跑为 2 passed，因此有效总结果为
  270 passed、3 skipped。
- `python -m ruff check src tests`：通过。
- `python -m mypy src`：通过。
- `npm run typecheck`：通过。
- `npm run test:frontend`：全部模块通过。
- `npm run build`：通过（仅保留既有的大 chunk 提示）。
- 真实 Streamable HTTP workflow：MCP health → create project → 读取动态 project resource →
  preflight (`valid: true`) → create simulation → step → delete，整条链路通过。

## 已知限制

- MCP 不承担 WebSocket/gRPC 的高频数据面职责。
- 尚未通过 MCP 上传 OpenUSD、加载 Python controller source 或下载二进制 artifact。
- Streamable HTTP transport 本身尚未接入 OAuth；远程公网部署必须由反向代理提供认证与 TLS。

## 下一步

- 设计经过用户确认的 artifact/blob 资源交换，而不是接受任意服务器文件路径。
- 为长时间导入/导出增加 MCP task/progress/cancellation 映射。
