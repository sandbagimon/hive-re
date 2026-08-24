# Robot Geometry Bundle and Asset Loading Performance

日期：2026-07-30  
提交：待提交

## 目标

消除机器人资产加载时逐 Visual 请求 JSON、重复解析大数组和浏览器现场计算法线造成的延迟，
同时保持旧 OpenUSD 缓存可用，并减少每个 Web Project 重复复制整套共享资产的成本。

## 主要改动

- 新增 `SIMGEOM1` Geometry Bundle v1：一个 articulation 的所有 Mesh Visual 写入一个
  content-addressed `.simbin` 文件。
- Bundle 使用小端紧凑数组：position/normal/UV 为 Float32、index 为 Uint32、RGB 为归一化
  Uint8；Header 保存 geometry ID、buffer slice 和预计算 bounds/sphere。
- 法线从 Three.js 运行时移到 OpenUSD 导入阶段计算，避免每次场景重建重复遍历三角面。
- `Articulation.visual_bundle` 作为项目相对引用进入 Robotics Model，并由 ResourceManager
  转换为 project-scoped opaque Artifact ID；多机器人场景可各自持有 bundle。
- 前端增加严格边界校验的 bundle decoder，单次获取 ArrayBuffer 后直接构造 typed
  BufferAttribute，并按 Artifact ID 缓存解码结果。
- 保留旧 `visual_cache`/`getVisualGeometry` 回退，新前端仍可打开已有逐 Mesh JSON 项目。
- Artifact 响应增加 ETag、条件请求与 immutable cache；旧大型 JSON API 增加 GZip 压缩。
- Robot Manifest 升级到 v4，记录 bundle format、内容地址和源 USD SHA-256。
- 导入成功后删除同一机器人可再生的旧 `visuals/*/visual.json`，不删除源 USD 与 collider。
- 新建 Project 优先使用文件系统 CoW clone，不支持时使用只读 cache hard link，再回退普通复制；
  `assets/external` 开发下载原件不再复制进每个 Project。
- OpenUSD cache 与 metadata 写入改为同目录临时文件 + atomic replace，确保共享 hard link 不会
  让项目内导入覆盖 seed asset。

## 性能结果

Franka Panda 实测：

| 指标 | 优化前 | 优化后 |
|---|---:|---:|
| 几何 HTTP 请求 | 29 | 1 |
| 视觉几何传输 | 15,859,941 B | 4,848,763 B |
| 传输缩减 | — | 69.4% |
| 几何数量 | 29 | 29 |
| 顶点数量 | 120,497 | 120,497 |
| 三角面数量 | 131,949 | 131,949 |

本地 seed Project 创建实测约 0.29 秒，Asset Catalog 读取约 0.02 秒；Project 中没有复制
`assets/external`。具体时间受文件系统是否支持 reflink、磁盘缓存和资产规模影响。

## 验证

- Python bundle 测试覆盖 magic/header、slice、法线、颜色压缩、UV、bounds 和体积回归。
- 前端 Node 测试覆盖合法 bundle typed-array 解码和非法 magic 拒绝。
- API 测试覆盖 opaque Artifact、二进制内容、ETag、immutable cache 与 304 条件响应。
- ResourceManager 测试覆盖 external 排除、共享 cache 和 atomic replace 后的 seed 独立性。
- Franka cache 重新生成后无逐 Visual JSON，几何/顶点/三角面计数与优化前一致。
- Python 非端口回归 232 passed、3 skipped；前端单测、TypeScript、Ruff、Mypy 和 Vite build 通过。
- 当前执行沙箱禁止绑定本机 socket，因此两项 gRPC 端口测试和 Playwright 服务端复跑未在本轮
  环境执行；失败原因是 `socket: operation not permitted`，不是契约断言失败。

## 已知限制

- Bundle v1 是 BeeFoundrySim 内部格式，尚未提供公开稳定规范或独立转换 CLI。
- 前后端目前都以完整文件处理 ArrayBuffer；尚未使用 Range、流式解析或 Web Worker。
- bundle cache 当前按 Artifact ID 保留到页面生命周期结束，大量不同项目连续打开时需要 LRU。
- 单刚体 OpenUSD 仍使用 `visual.json` 兼容链路，尚未统一迁移到 bundle。
- 高精度视觉网格的 GPU 上传与 draw call 数量没有因本次传输优化自动降低。

## 下一步

- 将 bundle 解码和法线/切线补全迁移到 Web Worker，并加入加载进度与取消。
- 增加 LOD、mesh merge/instancing 和 GPU/CPU memory telemetry。
- 评估单刚体缓存迁移、HTTP Range 与服务端流式文件响应。
- 为 100k、1M、10M 三角面资产建立导入、传输、解析和首帧基准。
