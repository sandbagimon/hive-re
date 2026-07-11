# Platform Audit & Roadmap Refresh

日期：2026-07-10
提交：审计现有模块进度、对比竞品差距、更新路线图

## 目标

- 盘点所有模块的实现状态（对照 PRODUCT_PLAN.md M0-M12 和 PLATFORM_GAP_MATRIX.md A-D 区）。
- 与 OrcaLab、Isaac Sim/Isaac Lab 公开能力做逐模块对比。
- 更新 PRODUCT_PLAN.md 和 PLATFORM_GAP_MATRIX.md，形成可执行的阶段性路线图。
- 修正过时的数据（测试数量等）。

## 主要改动

### 文档更新

- **PRODUCT_PLAN.md**：
  - 修正测试数量：36 passed + 1 skipped（原 37 passed 有误）。
  - 迭代计划区重新编排：标记 7 个已完成迭代（A/B/C/F、TS Migration、Preflight、OpenUSD Import）。
  - 新增「当前进度总览」表：12 个里程碑的状态、完成度百分比和一句话说明。
  - 新增「与竞品的差距快照」：9 个维度对比 SimLab/OrcaLab/Isaac Sim。
  - 新增「阶段性路线图 Gate 1-4」：4 个 Gate × 4-8 项任务，含优先级、预估工作量和验收标准。
  - 新增「差异化策略」：阐明不追 RTX、不追云、追 MuJoCo 轻量 + local-first 的定位。
- **PLATFORM_GAP_MATRIX.md**：
  - 新增「2026-07-10 审计更新」段：代码规模、Gate 状态、最大落差、差异化窗口。
- **README.md**：
  - Next Milestone 改为 Gate 1 的 6 项具体任务。

### 代码库扫描结果

| 区域 | 文件 | 行数 |
|------|------|------|
| Python models | 3 文件 | ~136 |
| Python services | 10 文件 | ~1,465 |
| TypeScript | 7 文件 | ~1,395 |
| 测试 | 7 文件 | ~4,000 |
| **合计** | **27 文件** | **~6,996** |

## 验证

- `pytest`：36 passed，1 skipped
- TypeScript typecheck：passed
- `ruff`：passed

## 核心结论

1. **SimLab 已越过"只有 UI 原型"阶段**：primitive scene authoring、TS 编辑器状态、MJCF preflight、MuJoCo 运行和 viewport pose sync 形成小型闭环。
2. **最大阻塞是机器人仿真闭环（Gate 1）**：scene model 不支持 articulation、没有 MJCF import、没有 controller API、没有 sensor runtime。
3. **与 OrcaLab 最大落差**：robot articulation、sensor 体系、训练环境、控制器 API（都在 Gate 1 + Gate 3 范围内）。
4. **与 Isaac Sim 最大落差**：RTX 渲染、OpenUSD 原生、传感器/标注器生态、GPU 并行（Gate 4 范围，短期不追）。
5. **差异化优势**：MuJoCo 轻量可复现 + local-first + 人类可读文本格式（scene.json/MJCF），适合研究和快速迭代。

## 下一步

立即启动 Gate 1 第一项任务：

1. **Robot/Link/Joint/Actuator/Sensor 共享 schema**（3-4 天）— 这是后续所有 robot import、state bridge、controller 的数据契约基础。
2. 然后并行推进 MJCF importer 和 scene hierarchy 扩展。
