# Codex OpenUSD Articulation 执行路线

日期：2026-07-14  
提交：未提交

## 目标

为迁移到新的开发环境提供一份可由 Codex 直接执行的交接文档，并把近期开发焦点从普通
OpenUSD mesh 导入明确调整为 OpenUSD Physics/Articulation 到可控 MuJoCo 车辆的垂直闭环。

## 主要改动

- 新增 `docs/CODEX_EXECUTION_ROADMAP.md`。
- 记录当前实际测试基线和 OpenUSD importer 的真实能力边界。
- 定义不可破坏的 clean-room、状态所有权、统一中间模型和显式导入损失报告约束。
- 将 Gate 1 拆分为：
  - Gate 1A：OpenUSD Articulation 导入；
  - Gate 1B：MJCF 转换、运行时状态和固定步长时钟；
  - Gate 1C：WASD 车辆控制闭环。
- 明确新环境第一项任务只实现 Robotics Intermediate Model、schema、验证和 round-trip 测试。
- 在 README 和 Product Plan 中增加当前执行路线入口。

## 验证

- `git diff --check`：未发现 patch 格式错误；Git 仅提示 Windows 工作区未来可能进行 LF/CRLF
  转换。
- 本次仅修改 Markdown，没有修改运行时代码，因此未重复运行完整测试套件。
- 路线中记录的最近实际基线为：pytest 34 passed/2 skipped，ruff 和 mypy 通过，frontend store
  测试通过；TypeScript typecheck 因当前环境缺少 `tsc` 未被视为通过。

## 已知限制

- 路线尚未实现任何 Robotics schema、USD Joint importer 或车辆控制代码。
- 最小 OpenUSD 小车 fixture 的来源/许可证或程序化生成方式仍需在 Gate 1A.1 决定。
- MJCF importer 和 URDF importer 保留在长期范围，但排在 USD 小车垂直闭环之后。

## 下一步

按照 `CODEX_EXECUTION_ROADMAP.md` 第 10 节，实现版本化 Robotics Intermediate Model 和
`shared/schemas/robotics.schema.json`，暂不修改 importer、exporter 和 UI。

